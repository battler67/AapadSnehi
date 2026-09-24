from __future__ import annotations

import json
import math
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from ..models import (
    EdgeDevice,
    EdgeFeatureSnapshot,
    EdgeMeasurement,
    EdgeObservation,
    EdgeRiskAssessment,
    EdgeRiskEvent,
    EdgeRiskReview,
    EdgeRiskTransition,
    Incident,
    Source,
)
from ..priority import compute_priority
from ..services.normalizer import HAZARD_DEFAULT_NEEDS
from .catalog import edge_config, property_definition, region_definition
from .chronos import RollingForecastAdapter
from .detectors import DetectorResult, evaluate_hazard, routed_hazards
from .features import FEATURE_PIPELINE_VERSION, FeatureResult, build_features
from .schemas import DeviceCreate, RiskEventReviewCreate, TelemetryEnvelope


DEMO_LABEL = "SIMULATED / DEMO ONLY"


class EdgeNotFoundError(LookupError):
    pass


class EdgeConflictError(ValueError):
    pass


class EdgeValidationError(ValueError):
    pass


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _aware(value: datetime) -> datetime:
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


def _json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def _loads(value: str, fallback: Any) -> Any:
    try:
        parsed = json.loads(value)
        return parsed
    except (TypeError, json.JSONDecodeError):
        return fallback


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    radius = 6371.0088
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lon2 - lon1)
    value = math.sin(delta_phi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda / 2) ** 2
    return radius * 2 * math.atan2(math.sqrt(value), math.sqrt(1 - value))


def register_device(db: Session, payload: DeviceCreate, *, idempotent: bool = False) -> EdgeDevice:
    existing = db.get(EdgeDevice, payload.device_id)
    if existing:
        if idempotent:
            return existing
        raise EdgeConflictError("A device with this deviceId already exists")
    device = EdgeDevice(
        device_id=payload.device_id,
        name=payload.name,
        device_type=payload.device_type,
        installed_purposes_json=_json(payload.installed_purposes),
        capabilities_json=_json(payload.capabilities),
        region_id=payload.region_id,
        latitude=payload.location.latitude,
        longitude=payload.location.longitude,
        elevation_m=payload.location.elevation_m,
        expected_interval_seconds=payload.expected_interval_seconds,
        simulation_only=payload.simulation_only,
    )
    db.add(device)
    db.commit()
    db.refresh(device)
    return device


def _observation_payload(observation: EdgeObservation) -> dict[str, Any]:
    return {
        "id": observation.id,
        "timestamp": _aware(observation.event_time),
        "measurements": {measurement.property_name: measurement.value for measurement in observation.measurements},
        "deviceHealth": {
            "batteryPct": observation.battery_pct,
            "signalQualityPct": observation.signal_quality_pct,
        },
        "qualityFlags": _loads(observation.quality_flags_json, []),
    }


def _recent_observations(db: Session, device_id: str, as_of: datetime) -> list[dict[str, Any]]:
    observations = db.scalars(
        select(EdgeObservation)
        .options(selectinload(EdgeObservation.measurements))
        .where(
            EdgeObservation.device_id == device_id,
            EdgeObservation.event_time <= as_of,
            EdgeObservation.event_time >= as_of - timedelta(minutes=60),
        )
        .order_by(EdgeObservation.event_time, EdgeObservation.id)
    ).all()
    return [_observation_payload(item) for item in observations]


def _quality_flags(device: EdgeDevice, envelope: TelemetryEnvelope) -> list[str]:
    flags: list[str] = []
    if device.high_water_sequence >= 0:
        if envelope.sequence_number > device.high_water_sequence + 1:
            flags.append("sequence_gap")
        elif envelope.sequence_number < device.high_water_sequence:
            flags.append("out_of_order")
    if envelope.device_health.battery_pct < 20:
        flags.append("low_battery")
    if envelope.device_health.signal_quality_pct < 25:
        flags.append("weak_signal")
    submitted = {name for name, value in envelope.measurements.items() if value is not None}
    capabilities = set(_loads(device.capabilities_json, []))
    if submitted != capabilities:
        flags.append("missing_measurements")
    return flags


def _validate_against_registry(db: Session, envelope: TelemetryEnvelope) -> EdgeDevice:
    device = db.get(EdgeDevice, envelope.device_id)
    if not device:
        raise EdgeNotFoundError("Register the device before sending telemetry")
    if device.device_type != envelope.device_type:
        raise EdgeValidationError("deviceType does not match the registry")
    if haversine_km(
        device.latitude, device.longitude, envelope.location.latitude, envelope.location.longitude
    ) > 0.5:
        raise EdgeValidationError("Telemetry location is more than 500 m from the registered location")
    capabilities = set(_loads(device.capabilities_json, []))
    submitted = set(envelope.measurements)
    unsupported = sorted(submitted - capabilities)
    if unsupported:
        raise EdgeValidationError(f"Measurements exceed registered capabilities: {unsupported}")
    now = _now()
    if envelope.timestamp > now + timedelta(minutes=5):
        raise EdgeValidationError("Future-dated telemetry exceeds the five-minute allowance")
    if envelope.timestamp < now - timedelta(hours=24):
        raise EdgeValidationError("Stale telemetry exceeds the 24-hour allowance")
    if db.scalar(select(EdgeObservation.id).where(EdgeObservation.message_id == str(envelope.message_id))):
        raise EdgeConflictError("Duplicate messageId")
    if db.scalar(
        select(EdgeObservation.id).where(
            EdgeObservation.device_id == envelope.device_id,
            EdgeObservation.sequence_number == envelope.sequence_number,
        )
    ):
        raise EdgeConflictError("Duplicate sequenceNumber for this device")
    return device


def _anomaly_score(hazard: str, observations: list[dict[str, Any]]) -> float:
    property_name = {
        "flood": "waterLevelM",
        "landslide": "poreWaterPressureKpa",
        "tsunami": "seaLevelAnomalyM",
    }[hazard]
    values = [
        float(item["measurements"][property_name])
        for item in observations
        if item["measurements"].get(property_name) is not None
    ]
    return RollingForecastAdapter().anomaly_score(values)


def _nearby_agreement(
    db: Session, device: EdgeDevice, hazard: str, as_of: datetime, threshold: float = 0.35
) -> int:
    radius = float(edge_config()["hazards"][hazard]["nearbyKm"])
    recent = db.scalars(
        select(EdgeRiskAssessment)
        .where(
            EdgeRiskAssessment.hazard == hazard,
            EdgeRiskAssessment.device_id != device.device_id,
            EdgeRiskAssessment.as_of >= as_of - timedelta(minutes=10),
            EdgeRiskAssessment.probability >= threshold,
        )
        .order_by(EdgeRiskAssessment.as_of.desc())
    ).all()
    agreed: set[str] = set()
    for assessment in recent:
        if assessment.device_id in agreed:
            continue
        other = db.get(EdgeDevice, assessment.device_id)
        if other and haversine_km(device.latitude, device.longitude, other.latitude, other.longitude) <= radius:
            agreed.add(other.device_id)
    return len(agreed)


def _store_feature_and_assessment(
    db: Session,
    device: EdgeDevice,
    hazard: str,
    feature_result: FeatureResult,
    detector: DetectorResult,
) -> tuple[EdgeFeatureSnapshot, EdgeRiskAssessment]:
    snapshot = db.scalar(
        select(EdgeFeatureSnapshot).where(
            EdgeFeatureSnapshot.device_id == device.device_id,
            EdgeFeatureSnapshot.hazard == hazard,
            EdgeFeatureSnapshot.as_of == feature_result.as_of,
        )
    )
    if snapshot is None:
        snapshot = EdgeFeatureSnapshot(
            device_id=device.device_id,
            hazard=hazard,
            as_of=feature_result.as_of,
            pipeline_version=FEATURE_PIPELINE_VERSION,
            features_json=_json(feature_result.features),
            observation_ids_json=_json(feature_result.observation_ids),
            data_quality=feature_result.data_quality,
        )
        db.add(snapshot)
        db.flush()
    else:
        snapshot.features_json = _json(feature_result.features)
        snapshot.observation_ids_json = _json(feature_result.observation_ids)
        snapshot.data_quality = feature_result.data_quality
    assessment = db.scalar(
        select(EdgeRiskAssessment).where(EdgeRiskAssessment.feature_snapshot_id == snapshot.id)
    )
    values = {
        "device_id": device.device_id,
        "feature_snapshot_id": snapshot.id,
        "hazard": hazard,
        "as_of": feature_result.as_of,
        "probability": detector.probability,
        "rule_score": detector.rule_score,
        "classifier_probability": detector.classifier_probability,
        "anomaly_score": detector.anomaly_score,
        "confidence": detector.confidence,
        "risk_level": detector.risk_level,
        "data_quality": detector.data_quality,
        "agreement_count": 0,
        "model_version": detector.model_version,
        "model_status": detector.model_status,
        "contributors_json": _json(detector.top_contributors),
    }
    if assessment is None:
        assessment = EdgeRiskAssessment(**values)
        db.add(assessment)
        db.flush()
    else:
        for name, value in values.items():
            setattr(assessment, name, value)
    return snapshot, assessment


def _consecutive_count(db: Session, device_id: str, hazard: str, threshold: float, above: bool) -> int:
    recent = db.scalars(
        select(EdgeRiskAssessment)
        .where(EdgeRiskAssessment.device_id == device_id, EdgeRiskAssessment.hazard == hazard)
        .order_by(EdgeRiskAssessment.as_of.desc(), EdgeRiskAssessment.id.desc())
        .limit(4)
    ).all()
    count = 0
    for item in recent:
        matches = item.probability >= threshold if above else item.probability < threshold
        if not matches:
            break
        count += 1
    return count


def _desired_state(
    db: Session,
    assessment: EdgeRiskAssessment,
    features: dict[str, float],
) -> tuple[str, str]:
    policy = edge_config()["hazards"][assessment.hazard]
    critical_count = _consecutive_count(db, assessment.device_id, assessment.hazard, policy["critical"], True)
    warning_count = _consecutive_count(db, assessment.device_id, assessment.hazard, policy["warning"], True)
    watch_count = _consecutive_count(db, assessment.device_id, assessment.hazard, policy["watch"], True)
    extreme_tsunami = assessment.hazard == "tsunami" and (
        features.get("earthquakeMagnitude_current", 0) >= 7
        and abs(features.get("seaLevelAnomalyM_current", 0)) >= 0.8
    )
    if extreme_tsunami:
        return "CRITICAL", "configured extreme pressure/sea-level anomaly with simulated seismic corroboration"
    if critical_count >= 3 and assessment.agreement_count >= 1:
        return "CRITICAL", "three critical windows with nearby device agreement"
    if warning_count >= 3 or (warning_count >= 2 and assessment.agreement_count >= 1):
        return "WARNING", "sustained warning windows with sufficient temporal or nearby agreement"
    if watch_count >= 2:
        return "WATCH", "two consecutive watch-level windows"
    return "NORMAL", "risk is below the configured escalation persistence"


def _event_evidence(
    device: EdgeDevice,
    snapshot: EdgeFeatureSnapshot,
    assessment: EdgeRiskAssessment,
    reason: str,
) -> dict[str, Any]:
    return {
        "notice": DEMO_LABEL,
        "deviceIds": [device.device_id],
        "observationIds": _loads(snapshot.observation_ids_json, []),
        "featureSnapshotId": snapshot.id,
        "features": _loads(snapshot.features_json, {}),
        "assessmentId": assessment.id,
        "ruleVersion": f"{assessment.hazard}-rules-v1",
        "modelVersion": assessment.model_version,
        "featurePipelineVersion": snapshot.pipeline_version,
        "confidence": assessment.confidence,
        "dataQuality": assessment.data_quality,
        "reason": reason,
        "asOf": _aware(assessment.as_of).isoformat(),
        "simulated": True,
    }


def _update_event_state(
    db: Session,
    device: EdgeDevice,
    snapshot: EdgeFeatureSnapshot,
    assessment: EdgeRiskAssessment,
) -> EdgeRiskEvent | None:
    desired, reason = _desired_state(db, assessment, _loads(snapshot.features_json, {}))
    event_key = f"{device.region_id}:{assessment.hazard}"
    event = db.scalar(
        select(EdgeRiskEvent)
        .where(EdgeRiskEvent.event_key == event_key, EdgeRiskEvent.active.is_(True))
        .order_by(EdgeRiskEvent.updated_at.desc())
    )
    if event is None and desired == "NORMAL":
        return None
    evidence = _event_evidence(device, snapshot, assessment, reason)
    now = _aware(assessment.as_of)
    if event is None:
        event = EdgeRiskEvent(
            event_key=event_key,
            hazard=assessment.hazard,
            region_id=device.region_id,
            state=desired,
            probability=assessment.probability,
            confidence=assessment.confidence,
            data_quality=assessment.data_quality,
            contributing_device_ids_json=_json([device.device_id]),
            latest_assessment_ids_json=_json([assessment.id]),
            evidence_json=_json(evidence),
            first_seen_at=now,
            last_transition_at=now,
            updated_at=now,
        )
        db.add(event)
        db.flush()
        db.add(
            EdgeRiskTransition(
                event_id=event.id,
                from_state="NORMAL",
                to_state=desired,
                reason=reason,
                probability=assessment.probability,
                confidence=assessment.confidence,
                evidence_json=_json(evidence),
                transitioned_at=now,
            )
        )
        return event

    current = event.state
    next_state = current
    ranks = {"NORMAL": 0, "RECOVERY": 1, "WATCH": 2, "WARNING": 3, "CRITICAL": 4}
    if ranks.get(desired, 0) > ranks.get(current, 0):
        next_state = desired
    else:
        policy = edge_config()["hazards"][assessment.hazard]
        if current == "CRITICAL" and _consecutive_count(
            db, assessment.device_id, assessment.hazard, policy["exitCritical"], False
        ) >= 3:
            next_state, reason = "WARNING", "risk stayed below the critical exit threshold"
        elif current == "WARNING" and _consecutive_count(
            db, assessment.device_id, assessment.hazard, policy["exitWarning"], False
        ) >= 3:
            next_state, reason = "RECOVERY", "risk stayed below the warning exit threshold"
        elif current in {"WATCH", "RECOVERY"} and _consecutive_count(
            db, assessment.device_id, assessment.hazard, policy["exitWatch"], False
        ) >= 3:
            next_state, reason = "NORMAL", "risk stayed below the watch exit threshold"

    devices = set(_loads(event.contributing_device_ids_json, []))
    devices.add(device.device_id)
    event.probability = assessment.probability
    event.confidence = assessment.confidence
    event.data_quality = assessment.data_quality
    event.contributing_device_ids_json = _json(sorted(devices))
    event.latest_assessment_ids_json = _json([assessment.id])
    evidence["reason"] = reason
    event.evidence_json = _json(evidence)
    event.updated_at = now
    if next_state != current:
        event.state = next_state
        event.last_transition_at = now
        if next_state == "NORMAL":
            event.active = False
        db.add(
            EdgeRiskTransition(
                event_id=event.id,
                from_state=current,
                to_state=next_state,
                reason=reason,
                probability=assessment.probability,
                confidence=assessment.confidence,
                evidence_json=_json(evidence),
                transitioned_at=now,
            )
        )
    return event


def ingest_telemetry(db: Session, envelope: TelemetryEnvelope, *, source_protocol: str = "http") -> dict[str, Any]:
    device = _validate_against_registry(db, envelope)
    previous_event_at = _aware(device.last_event_at) if device.last_event_at else None
    flags = _quality_flags(device, envelope)
    simulation = envelope.simulation.model_dump(by_alias=True) if envelope.simulation else {}
    normalized = envelope.model_dump(mode="json", by_alias=True, exclude={"simulation"})
    run_id = envelope.simulation.run_id if envelope.simulation and envelope.simulation.run_id else None
    observation = EdgeObservation(
        message_id=str(envelope.message_id),
        device_id=envelope.device_id,
        run_id=run_id,
        schema_version=envelope.schema_version,
        device_type=envelope.device_type,
        event_time=envelope.timestamp,
        sequence_number=envelope.sequence_number,
        battery_pct=envelope.device_health.battery_pct,
        signal_quality_pct=envelope.device_health.signal_quality_pct,
        source_protocol=source_protocol,
        quality_flags_json=_json(flags),
        normalized_payload_json=_json(normalized),
        simulation_metadata_json=_json(simulation),
    )
    db.add(observation)
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise EdgeConflictError("Duplicate telemetry packet") from exc
    for name, value in envelope.measurements.items():
        if value is None:
            continue
        definition = property_definition(name)
        db.add(
            EdgeMeasurement(
                observation_id=observation.id,
                property_name=name,
                value=float(value),
                unit=str(definition["unit"]),
            )
        )
    device.last_seen_at = _now()
    device.last_event_at = max(previous_event_at, envelope.timestamp) if previous_event_at else envelope.timestamp
    device.high_water_sequence = max(device.high_water_sequence, envelope.sequence_number)
    device.battery_pct = envelope.device_health.battery_pct
    device.signal_quality_pct = envelope.device_health.signal_quality_pct
    device.status = "degraded" if flags else "online"
    penalty = 0.12 * len({"sequence_gap", "out_of_order", "missing_measurements"}.intersection(flags))
    device.trust_score = max(0.2, min(1.0, 0.6 + 0.002 * device.battery_pct + 0.002 * device.signal_quality_pct - penalty))
    db.flush()

    as_of = _aware(device.last_event_at)
    recent = _recent_observations(db, device.device_id, as_of)
    updates: list[dict[str, Any]] = []
    is_online_event = previous_event_at is None or envelope.timestamp >= previous_event_at
    for hazard in routed_hazards(device):
        feature_result = build_features(
            recent,
            capabilities=_loads(device.capabilities_json, []),
            as_of=as_of,
            expected_interval_seconds=device.expected_interval_seconds,
        )
        base_quality = feature_result.data_quality * device.trust_score
        agreement = _nearby_agreement(db, device, hazard, as_of)
        feature_result.features["nearby_device_anomaly_count"] = float(agreement)
        context = region_definition(device.region_id)["context"].get(hazard, 0.0)
        detector = evaluate_hazard(
            hazard,
            feature_result.features,
            data_quality=base_quality,
            anomaly_score=_anomaly_score(hazard, recent),
            geographic_relevance=float(context),
            agreement_count=agreement,
        )
        snapshot, assessment = _store_feature_and_assessment(db, device, hazard, feature_result, detector)
        assessment.agreement_count = agreement
        event = _update_event_state(db, device, snapshot, assessment) if is_online_event else None
        updates.append(
            {
                "assessmentId": assessment.id,
                "hazard": hazard,
                "probability": detector.probability,
                "riskLevel": detector.risk_level,
                "confidence": detector.confidence,
                "modelVersion": detector.model_version,
                "modelStatus": detector.model_status,
                "topContributors": detector.top_contributors,
                "dataQuality": detector.data_quality,
                "ruleScore": detector.rule_score,
                "classifierProbability": detector.classifier_probability,
                "anomalyScore": detector.anomaly_score,
                "nearbyAgreement": agreement,
                "eventId": event.id if event else None,
                "simulated": True,
            }
        )
    db.commit()
    return {
        "accepted": True,
        "messageId": str(envelope.message_id),
        "observationId": observation.id,
        "qualityFlags": flags,
        "riskUpdates": updates,
        "simulationMetadataUsedForInference": False,
    }


def promote_or_review_event(
    db: Session, event: EdgeRiskEvent, payload: RiskEventReviewCreate
) -> EdgeRiskEvent:
    if payload.action == "promote_to_incident" and event.incident_id is not None:
        raise EdgeConflictError("This risk event is already linked to an incident")
    review = EdgeRiskReview(
        event_id=event.id,
        action=payload.action,
        reviewer_name=payload.reviewer_name,
        note=payload.note,
        confirm_demo_only=payload.confirm_demo_only,
    )
    db.add(review)
    event.review_status = payload.action
    if payload.action == "dismiss":
        event.review_status = "dismissed"
    elif payload.action == "acknowledge":
        event.review_status = "acknowledged"
    else:
        source = db.scalar(select(Source).where(Source.slug == "edge-simulation"))
        if source is None:
            source = Source(
                slug="edge-simulation",
                name="Simulated edge early warning",
                adapter_type="edge_simulation",
                authority=DEMO_LABEL,
                source_kind="simulation",
                enabled=True,
                status="healthy",
            )
            db.add(source)
            db.flush()
        region = region_definition(event.region_id)
        severity = {"WATCH": 2, "WARNING": 4, "CRITICAL": 5, "RECOVERY": 2}.get(event.state, 2)
        needs = list(HAZARD_DEFAULT_NEEDS.get(event.hazard, ()))
        score, breakdown = compute_priority(
            severity=severity,
            occurred_at=event.last_transition_at,
            affected_estimate=0,
            needs=needs,
            verification_status="unverified",
            response_coverage=0,
        )
        incident = Incident(
            source_id=source.id,
            external_id=f"edge-risk-{event.id}",
            title=f"{DEMO_LABEL}: estimated {event.hazard} risk",
            description=(
                f"{DEMO_LABEL}. AapadSnehi estimated {event.hazard} risk from synthetic edge-device "
                "telemetry. This is not an official warning and requires human operational review."
            ),
            disaster_type=event.hazard,
            severity=severity,
            latitude=float(region["latitude"]),
            longitude=float(region["longitude"]),
            location_name=str(region["name"]),
            occurred_at=event.last_transition_at,
            source_kind="simulation",
            verification_status="unverified",
            affected_estimate=0,
            needs_json=_json(needs),
            priority_score=score,
            priority_breakdown_json=_json(breakdown),
            is_active=True,
        )
        db.add(incident)
        db.flush()
        event.incident_id = incident.id
        event.review_status = "promoted_to_incident"
    event.updated_at = _now()
    db.commit()
    db.refresh(event)
    return event
