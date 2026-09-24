from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import and_, func, select
from sqlalchemy.orm import Session, selectinload

from ..database import get_db
from ..models import (
    EdgeDevice,
    EdgeObservation,
    EdgeRiskAssessment,
    EdgeRiskEvent,
    EdgeRiskReview,
    EdgeRiskTransition,
    EdgeSimulationRun,
)
from .cap import export_cap
from .catalog import edge_config, region_catalog, scenario_catalog
from .schemas import DeviceCreate, RiskEventReviewCreate, SimulationCreate, TelemetryEnvelope
from .service import (
    DEMO_LABEL,
    EdgeConflictError,
    EdgeNotFoundError,
    EdgeValidationError,
    ingest_telemetry,
    promote_or_review_event,
    register_device,
)
from .simulator import simulation_manager


router = APIRouter(prefix="/api/edge", tags=["edge early warning"])


def _loads(raw: str, fallback: Any) -> Any:
    try:
        return json.loads(raw)
    except (TypeError, json.JSONDecodeError):
        return fallback


def _iso(value: datetime | None) -> str | None:
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat()


def device_dict(device: EdgeDevice) -> dict[str, Any]:
    return {
        "deviceId": device.device_id,
        "name": device.name,
        "deviceType": device.device_type,
        "installedPurposes": _loads(device.installed_purposes_json, []),
        "capabilities": _loads(device.capabilities_json, []),
        "regionId": device.region_id,
        "location": {"latitude": device.latitude, "longitude": device.longitude, "elevationM": device.elevation_m},
        "expectedIntervalSeconds": device.expected_interval_seconds,
        "simulationOnly": device.simulation_only,
        "status": device.status,
        "lastSeenAt": _iso(device.last_seen_at),
        "lastEventAt": _iso(device.last_event_at),
        "batteryPct": device.battery_pct,
        "signalQualityPct": device.signal_quality_pct,
        "trustScore": device.trust_score,
    }


def observation_dict(item: EdgeObservation) -> dict[str, Any]:
    return {
        "id": item.id,
        "messageId": item.message_id,
        "deviceId": item.device_id,
        "timestamp": _iso(item.event_time),
        "receivedAt": _iso(item.received_at),
        "sequenceNumber": item.sequence_number,
        "measurements": {
            measurement.property_name: {"value": measurement.value, "unit": measurement.unit}
            for measurement in item.measurements
        },
        "deviceHealth": {"batteryPct": item.battery_pct, "signalQualityPct": item.signal_quality_pct},
        "qualityFlags": _loads(item.quality_flags_json, []),
        "sourceProtocol": item.source_protocol,
        "simulated": bool(_loads(item.simulation_metadata_json, {})),
    }


def assessment_dict(item: EdgeRiskAssessment) -> dict[str, Any]:
    return {
        "assessmentId": item.id,
        "deviceId": item.device_id,
        "hazard": item.hazard,
        "asOf": _iso(item.as_of),
        "probability": item.probability,
        "riskLevel": item.risk_level,
        "confidence": item.confidence,
        "modelVersion": item.model_version,
        "modelStatus": item.model_status,
        "topContributors": _loads(item.contributors_json, []),
        "dataQuality": item.data_quality,
        "ruleScore": item.rule_score,
        "classifierProbability": item.classifier_probability,
        "anomalyScore": item.anomaly_score,
        "nearbyAgreement": item.agreement_count,
        "simulated": True,
    }


def event_dict(db: Session, event: EdgeRiskEvent, *, detailed: bool = False) -> dict[str, Any]:
    payload = {
        "id": event.id,
        "notice": DEMO_LABEL,
        "hazard": event.hazard,
        "regionId": event.region_id,
        "state": event.state,
        "probability": event.probability,
        "confidence": event.confidence,
        "dataQuality": event.data_quality,
        "contributingDeviceIds": _loads(event.contributing_device_ids_json, []),
        "simulated": True,
        "active": event.active,
        "reviewStatus": event.review_status,
        "incidentId": event.incident_id,
        "firstSeenAt": _iso(event.first_seen_at),
        "lastTransitionAt": _iso(event.last_transition_at),
        "updatedAt": _iso(event.updated_at),
    }
    if detailed:
        payload["evidence"] = _loads(event.evidence_json, {})
        payload["transitions"] = [
            {
                "id": item.id,
                "fromState": item.from_state,
                "toState": item.to_state,
                "reason": item.reason,
                "probability": item.probability,
                "confidence": item.confidence,
                "transitionedAt": _iso(item.transitioned_at),
            }
            for item in db.scalars(
                select(EdgeRiskTransition).where(EdgeRiskTransition.event_id == event.id).order_by(EdgeRiskTransition.transitioned_at)
            ).all()
        ]
        payload["reviews"] = [
            {"action": item.action, "reviewerName": item.reviewer_name, "note": item.note, "createdAt": _iso(item.created_at)}
            for item in db.scalars(select(EdgeRiskReview).where(EdgeRiskReview.event_id == event.id).order_by(EdgeRiskReview.created_at)).all()
        ]
    return payload


def run_dict(run: EdgeSimulationRun) -> dict[str, Any]:
    return {
        "runId": run.run_id,
        "scenario": run.scenario_id,
        "region": run.region_id,
        "seed": run.seed,
        "numberOfDevices": run.number_of_devices,
        "speedMultiplier": run.speed_multiplier,
        "timestepSeconds": run.timestep_seconds,
        "status": run.status,
        "cursorStep": run.cursor_step,
        "totalSteps": run.total_steps,
        "emittedCount": run.emitted_count,
        "rejectedCount": run.rejected_count,
        "error": run.error,
        "startedAt": _iso(run.started_at),
        "completedAt": _iso(run.completed_at),
    }


def _translate(exc: Exception) -> HTTPException:
    if isinstance(exc, EdgeNotFoundError | LookupError):
        return HTTPException(status_code=404, detail=str(exc))
    if isinstance(exc, EdgeConflictError):
        return HTTPException(status_code=409, detail=str(exc))
    return HTTPException(status_code=422, detail=str(exc))


@router.get("/catalog")
def catalog() -> dict[str, Any]:
    config = edge_config()
    return {"notice": config["notice"], "schemaVersion": "1.0", "profiles": config["profiles"], "properties": config["properties"], "regions": region_catalog(), "scenarios": scenario_catalog()}


@router.post("/devices", status_code=status.HTTP_201_CREATED)
def create_device(payload: DeviceCreate, db: Session = Depends(get_db)) -> dict[str, Any]:
    try:
        return device_dict(register_device(db, payload))
    except (EdgeConflictError, EdgeValidationError) as exc:
        raise _translate(exc) from exc


@router.get("/devices")
def list_devices(
    device_type: str | None = Query(default=None, alias="deviceType"),
    status_filter: str | None = Query(default=None, alias="status"),
    hazard: str | None = None,
    db: Session = Depends(get_db),
) -> list[dict[str, Any]]:
    query = select(EdgeDevice).order_by(EdgeDevice.device_id)
    if device_type:
        query = query.where(EdgeDevice.device_type == device_type)
    if status_filter:
        query = query.where(EdgeDevice.status == status_filter)
    devices = list(db.scalars(query).all())
    if hazard:
        devices = [item for item in devices if hazard in _loads(item.installed_purposes_json, [])]
    return [device_dict(item) for item in devices]


@router.get("/devices/{device_id}")
def get_device(device_id: str, db: Session = Depends(get_db)) -> dict[str, Any]:
    device = db.get(EdgeDevice, device_id)
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")
    return device_dict(device)


@router.post("/telemetry", status_code=status.HTTP_202_ACCEPTED)
def telemetry(payload: TelemetryEnvelope, db: Session = Depends(get_db)) -> dict[str, Any]:
    try:
        return ingest_telemetry(db, payload)
    except (EdgeNotFoundError, EdgeConflictError, EdgeValidationError) as exc:
        raise _translate(exc) from exc


@router.get("/observations/latest")
def latest_observations(db: Session = Depends(get_db)) -> list[dict[str, Any]]:
    latest = select(EdgeObservation.device_id, func.max(EdgeObservation.event_time).label("event_time")).group_by(EdgeObservation.device_id).subquery()
    rows = db.scalars(
        select(EdgeObservation).options(selectinload(EdgeObservation.measurements)).join(
            latest,
            and_(EdgeObservation.device_id == latest.c.device_id, EdgeObservation.event_time == latest.c.event_time),
        ).order_by(EdgeObservation.device_id)
    ).unique().all()
    return [observation_dict(item) for item in rows]


@router.get("/devices/{device_id}/observations")
def device_history(
    device_id: str,
    limit: int = Query(default=120, ge=1, le=2000),
    before: datetime | None = None,
    db: Session = Depends(get_db),
) -> list[dict[str, Any]]:
    if not db.get(EdgeDevice, device_id):
        raise HTTPException(status_code=404, detail="Device not found")
    query = select(EdgeObservation).options(selectinload(EdgeObservation.measurements)).where(EdgeObservation.device_id == device_id)
    if before:
        query = query.where(EdgeObservation.event_time <= before)
    rows = db.scalars(query.order_by(EdgeObservation.event_time.desc()).limit(limit)).unique().all()
    return [observation_dict(item) for item in reversed(rows)]


def _current_assessments(db: Session) -> list[EdgeRiskAssessment]:
    latest = select(EdgeRiskAssessment.device_id, EdgeRiskAssessment.hazard, func.max(EdgeRiskAssessment.as_of).label("as_of")).group_by(EdgeRiskAssessment.device_id, EdgeRiskAssessment.hazard).subquery()
    return list(db.scalars(select(EdgeRiskAssessment).join(latest, and_(EdgeRiskAssessment.device_id == latest.c.device_id, EdgeRiskAssessment.hazard == latest.c.hazard, EdgeRiskAssessment.as_of == latest.c.as_of))).all())


@router.get("/risks")
def current_risks(
    min_lat: float | None = Query(default=None, alias="minLat"),
    min_lon: float | None = Query(default=None, alias="minLon"),
    max_lat: float | None = Query(default=None, alias="maxLat"),
    max_lon: float | None = Query(default=None, alias="maxLon"),
    hazard: str | None = None,
    db: Session = Depends(get_db),
) -> list[dict[str, Any]]:
    rows = _current_assessments(db)
    result = []
    for item in rows:
        device = db.get(EdgeDevice, item.device_id)
        if hazard and item.hazard != hazard:
            continue
        if None not in (min_lat, min_lon, max_lat, max_lon) and not (min_lat <= device.latitude <= max_lat and min_lon <= device.longitude <= max_lon):
            continue
        result.append({**assessment_dict(item), "location": {"latitude": device.latitude, "longitude": device.longitude}})
    return result


@router.get("/events")
def list_events(active: bool | None = None, db: Session = Depends(get_db)) -> list[dict[str, Any]]:
    query = select(EdgeRiskEvent).order_by(EdgeRiskEvent.updated_at.desc()).limit(100)
    if active is not None:
        query = query.where(EdgeRiskEvent.active.is_(active))
    return [event_dict(db, item) for item in db.scalars(query).all()]


@router.get("/events/{event_id}")
def get_event(event_id: int, db: Session = Depends(get_db)) -> dict[str, Any]:
    event = db.get(EdgeRiskEvent, event_id)
    if not event:
        raise HTTPException(status_code=404, detail="Risk event not found")
    return event_dict(db, event, detailed=True)


@router.post("/events/{event_id}/review")
def review_event(event_id: int, payload: RiskEventReviewCreate, db: Session = Depends(get_db)) -> dict[str, Any]:
    event = db.get(EdgeRiskEvent, event_id)
    if not event:
        raise HTTPException(status_code=404, detail="Risk event not found")
    try:
        event = promote_or_review_event(db, event, payload)
    except EdgeConflictError as exc:
        raise _translate(exc) from exc
    return event_dict(db, event, detailed=True)


@router.get("/events/{event_id}/cap")
def cap_event(event_id: int, db: Session = Depends(get_db)) -> Response:
    event = db.get(EdgeRiskEvent, event_id)
    if not event:
        raise HTTPException(status_code=404, detail="Risk event not found")
    return Response(export_cap(event), media_type="application/cap+xml", headers={"Content-Disposition": f'attachment; filename="simulated-edge-event-{event.id}.xml"'})


@router.post("/simulations", status_code=status.HTTP_201_CREATED)
async def start_simulation(payload: SimulationCreate, db: Session = Depends(get_db)) -> dict[str, Any]:
    run_id = await simulation_manager.start(payload, db=db)
    return run_dict(db.get(EdgeSimulationRun, run_id))


@router.get("/simulations")
def list_simulations(db: Session = Depends(get_db)) -> list[dict[str, Any]]:
    return [run_dict(item) for item in db.scalars(select(EdgeSimulationRun).order_by(EdgeSimulationRun.started_at.desc()).limit(30)).all()]


@router.get("/simulations/{run_id}")
def get_simulation(run_id: str, db: Session = Depends(get_db)) -> dict[str, Any]:
    run = db.get(EdgeSimulationRun, run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Simulation run not found")
    return run_dict(run)


@router.post("/simulations/{run_id}/{action}")
async def control_simulation(run_id: str, action: Literal["pause", "resume", "stop", "reset"], db: Session = Depends(get_db)) -> dict[str, Any]:
    original = db.get(EdgeSimulationRun, run_id)
    if not original:
        raise HTTPException(status_code=404, detail="Simulation run not found")
    try:
        if action == "reset":
            simulation_manager.stop(run_id, db=db)
            prefix = f"sim-{run_id[:8]}-"
            for device in db.scalars(select(EdgeDevice).where(EdgeDevice.device_id.like(f"{prefix}%"))).all():
                device.status = "retired"
            reset_time = datetime.now(timezone.utc)
            for event in db.scalars(select(EdgeRiskEvent).where(EdgeRiskEvent.active.is_(True))).all():
                contributors = _loads(event.contributing_device_ids_json, [])
                if any(str(device_id).startswith(prefix) for device_id in contributors):
                    previous = event.state
                    event.state = "RECOVERY"
                    event.active = False
                    event.updated_at = reset_time
                    event.last_transition_at = reset_time
                    db.add(EdgeRiskTransition(event_id=event.id, from_state=previous, to_state="RECOVERY", reason="simulation reset; prior evidence retained", probability=event.probability, confidence=event.confidence, evidence_json=event.evidence_json, transitioned_at=reset_time))
            db.commit()
            request = SimulationCreate.model_validate_json(original.config_json)
            replacement_id = await simulation_manager.start(request, db=db)
            db.expire_all()
            return run_dict(db.get(EdgeSimulationRun, replacement_id))
        getattr(simulation_manager, action)(run_id, db=db)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    db.expire_all()
    return run_dict(db.get(EdgeSimulationRun, run_id))


@router.get("/snapshot")
def snapshot(cursor: str | None = None, db: Session = Depends(get_db)) -> dict[str, Any]:
    updated_since = None
    if cursor:
        try:
            updated_since = datetime.fromisoformat(cursor.replace("Z", "+00:00"))
        except ValueError as exc:
            raise HTTPException(status_code=422, detail="cursor must be an ISO-8601 timestamp") from exc
    event_query = select(EdgeRiskEvent).order_by(EdgeRiskEvent.updated_at.desc()).limit(100)
    if updated_since:
        event_query = event_query.where(EdgeRiskEvent.updated_at > updated_since)
    now = datetime.now(timezone.utc)
    devices = list(db.scalars(select(EdgeDevice).where(EdgeDevice.status != "retired").order_by(EdgeDevice.device_id)).all())
    active_device_ids = {item.device_id for item in devices}
    return {
        "notice": DEMO_LABEL,
        "cursor": now.isoformat(),
        "transport": "polling",
        "suggestedPollSeconds": 2,
        "devices": [device_dict(item) for item in devices],
        "risks": [assessment_dict(item) for item in _current_assessments(db) if item.device_id in active_device_ids],
        "events": [event_dict(db, item) for item in db.scalars(event_query).all()],
        "simulations": [run_dict(item) for item in db.scalars(select(EdgeSimulationRun).where(EdgeSimulationRun.started_at >= now - timedelta(days=1)).order_by(EdgeSimulationRun.started_at.desc()).limit(10)).all()],
    }
