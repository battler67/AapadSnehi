from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import uuid4
import time

import pytest
from pydantic import ValidationError

from app.edge.cap import CAP_NS, export_cap
from app.edge.chronos import ChronosBoltAdapter, RollingForecastAdapter
from app.edge.features import build_features
from app.edge.schemas import TelemetryEnvelope
from app.edge.simulator import _measurements
from app.models import EdgeDevice, EdgeFeatureSnapshot, EdgeRiskAssessment, EdgeRiskEvent
from app.edge.service import _desired_state, _update_event_state


def _device_payload(device_id: str) -> dict:
    return {
        "deviceId": device_id,
        "name": "Test river gauge",
        "deviceType": "river_gauge",
        "installedPurposes": ["flood"],
        "capabilities": ["rainfallMmH", "cumulativeRainfallMm", "waterLevelM", "waterLevelRiseMPerH", "flowVelocityMps", "soilMoisturePct", "temperatureC", "atmosphericPressureHpa"],
        "regionId": "assam_river",
        "location": {"latitude": 26.1445, "longitude": 91.7362, "elevationM": 54},
        "expectedIntervalSeconds": 60,
        "simulationOnly": True,
    }


def _packet(device_id: str, sequence: int, timestamp: datetime, message_id: str | None = None) -> dict:
    return {
        "schemaVersion": "1.0",
        "messageId": message_id or str(uuid4()),
        "deviceId": device_id,
        "deviceType": "river_gauge",
        "timestamp": timestamp.isoformat(),
        "sequenceNumber": sequence,
        "location": {"latitude": 26.1445, "longitude": 91.7362, "elevationM": 54},
        "measurements": {"rainfallMmH": 78, "cumulativeRainfallMm": 210, "waterLevelM": 7.4, "waterLevelRiseMPerH": 1.8, "flowVelocityMps": 5.2, "soilMoisturePct": 91, "temperatureC": 26, "atmosphericPressureHpa": 1001},
        "deviceHealth": {"batteryPct": 85, "signalQualityPct": 80},
        "simulation": {"scenarioId": "test-flood", "groundTruthState": "warning"},
    }


def test_schema_rejects_version_unknown_property_and_nonfinite():
    payload = _packet("schema-test", 1, datetime.now(timezone.utc))
    payload["schemaVersion"] = "9.0"
    with pytest.raises(ValidationError):
        TelemetryEnvelope.model_validate(payload)
    payload["schemaVersion"] = "1.0"
    payload["measurements"] = {"notAProperty": 2}
    with pytest.raises(ValidationError):
        TelemetryEnvelope.model_validate(payload)
    payload["measurements"] = {"waterLevelM": float("nan")}
    with pytest.raises(ValidationError):
        TelemetryEnvelope.model_validate(payload)


def test_feature_windows_do_not_use_future_observations():
    anchor = datetime(2026, 9, 2, 12, tzinfo=timezone.utc)
    observations = [
        {"id": 1, "timestamp": anchor - timedelta(minutes=1), "measurements": {"waterLevelM": 3.0}, "batteryPct": 90, "signalQualityPct": 90, "qualityFlags": []},
        {"id": 2, "timestamp": anchor, "measurements": {"waterLevelM": 4.0}, "batteryPct": 90, "signalQualityPct": 90, "qualityFlags": []},
        {"id": 3, "timestamp": anchor + timedelta(minutes=1), "measurements": {"waterLevelM": 99.0}, "batteryPct": 90, "signalQualityPct": 90, "qualityFlags": []},
    ]
    result = build_features(observations, capabilities=["waterLevelM"], as_of=anchor)
    assert result.features["waterLevelM_current"] == 4.0
    assert result.features["waterLevelM_5m_max"] == 4.0
    assert result.observation_ids == [1, 2]


def test_forecast_fallback_and_disabled_chronos(monkeypatch):
    assert RollingForecastAdapter().anomaly_score([1, 1, 1, 9]) > 0.5
    monkeypatch.setenv("AAPAD_EDGE_CHRONOS_ENABLED", "false")
    with pytest.raises(RuntimeError, match="disabled"):
        ChronosBoltAdapter()._load()


def test_http_ingestion_duplicate_out_of_order_and_end_to_end_risk(client):
    device_id = f"api-river-{uuid4().hex[:8]}"
    assert client.post("/api/edge/devices", json=_device_payload(device_id)).status_code == 201
    base = datetime.now(timezone.utc) - timedelta(minutes=8)
    duplicate_id = str(uuid4())
    first = client.post("/api/edge/telemetry", json=_packet(device_id, 1, base, duplicate_id))
    assert first.status_code == 202
    assert first.json()["simulationMetadataUsedForInference"] is False
    assert client.post("/api/edge/telemetry", json=_packet(device_id, 1, base, duplicate_id)).status_code == 409
    for sequence in range(3, 9):
        response = client.post("/api/edge/telemetry", json=_packet(device_id, sequence, base + timedelta(minutes=sequence)))
        assert response.status_code == 202
    out_of_order = client.post("/api/edge/telemetry", json=_packet(device_id, 2, base + timedelta(minutes=2)))
    assert out_of_order.status_code == 202
    assert "out_of_order" in out_of_order.json()["qualityFlags"]
    history = client.get(f"/api/edge/devices/{device_id}/observations").json()
    assert len(history) == 8
    risks = client.get("/api/edge/risks?hazard=flood").json()
    assert any(item["deviceId"] == device_id and 0 <= item["probability"] <= 1 for item in risks)
    snapshot = client.get("/api/edge/snapshot")
    assert snapshot.status_code == 200
    assert snapshot.json()["notice"] == "SIMULATED / DEMO ONLY"


def test_registry_rejects_measurements_outside_capabilities(client):
    device_id = f"cap-river-{uuid4().hex[:8]}"
    assert client.post("/api/edge/devices", json=_device_payload(device_id)).status_code == 201
    packet = _packet(device_id, 1, datetime.now(timezone.utc))
    packet["measurements"]["seaLevelAnomalyM"] = 1.2
    response = client.post("/api/edge/telemetry", json=packet)
    assert response.status_code == 422
    assert "capabilities" in response.json()["detail"]


def test_review_requires_explicit_demo_confirmation(client):
    from app.database import SessionLocal

    with SessionLocal() as db:
        event = EdgeRiskEvent(event_key=f"test:{uuid4()}", hazard="flood", region_id="assam_river", state="WARNING", probability=.75, confidence=.7, data_quality=.8, simulated=True, active=True)
        db.add(event); db.commit(); event_id = event.id
    denied = client.post(f"/api/edge/events/{event_id}/review", json={"action": "promote_to_incident", "reviewerName": "Test operator", "confirmDemoOnly": False})
    assert denied.status_code == 422
    promoted = client.post(f"/api/edge/events/{event_id}/review", json={"action": "promote_to_incident", "reviewerName": "Test operator", "confirmDemoOnly": True})
    assert promoted.status_code == 200
    body = promoted.json()
    assert body["incidentId"] is not None
    incident = next(item for item in client.get("/api/incidents").json() if item["id"] == body["incidentId"])
    assert "SIMULATED / DEMO ONLY" in incident["title"]
    assert incident["verificationStatus"] == "unverified"


def test_cap_export_is_test_only_and_complete():
    now = datetime.now(timezone.utc)
    event = EdgeRiskEvent(id=9, event_key="cap", hazard="tsunami", region_id="odisha_coast", state="CRITICAL", probability=.9, confidence=.8, data_quality=.9, updated_at=now, last_transition_at=now)
    xml = export_cap(event)
    assert CAP_NS in xml
    assert "<status>Test</status>" in xml
    assert "SIMULATED / DEMO ONLY" in xml
    for field in ("urgency", "severity", "certainty", "area", "effective", "expires", "instruction"):
        assert f"<{field}" in xml


def test_alert_policy_requires_consecutive_windows_and_applies_hysteresis():
    from app.database import SessionLocal
    import json

    key = uuid4().hex[:10]
    device_id = f"policy-{key}"
    region_id = f"test-region-{key}"
    now = datetime.now(timezone.utc)
    with SessionLocal() as db:
        device = EdgeDevice(device_id=device_id, name="Policy test", device_type="river_gauge", installed_purposes_json='["flood"]', capabilities_json='["waterLevelM"]', region_id=region_id, latitude=20, longitude=80, expected_interval_seconds=60)
        db.add(device); db.flush()
        assessments = []
        snapshots = []
        for index, probability in enumerate((.40, .41)):
            snapshot = EdgeFeatureSnapshot(device_id=device_id, hazard="flood", as_of=now + timedelta(minutes=index), pipeline_version="test", features_json="{}", observation_ids_json="[]", data_quality=.9)
            db.add(snapshot); db.flush()
            assessment = EdgeRiskAssessment(device_id=device_id, feature_snapshot_id=snapshot.id, hazard="flood", as_of=snapshot.as_of, probability=probability, rule_score=.4, classifier_probability=.4, anomaly_score=0, confidence=.8, risk_level="WATCH", data_quality=.9, agreement_count=0, model_version="test", contributors_json="[]")
            db.add(assessment); db.flush(); assessments.append(assessment); snapshots.append(snapshot)
        desired, _ = _desired_state(db, assessments[-1], {})
        assert desired == "WATCH"

        event = EdgeRiskEvent(event_key=f"{region_id}:flood", hazard="flood", region_id=region_id, state="WARNING", probability=.7, confidence=.8, data_quality=.9, contributing_device_ids_json=json.dumps([device_id]), latest_assessment_ids_json="[]", evidence_json="{}", active=True, first_seen_at=now, last_transition_at=now, updated_at=now)
        db.add(event)
        for index in range(2, 5):
            snapshot = EdgeFeatureSnapshot(device_id=device_id, hazard="flood", as_of=now + timedelta(minutes=index), pipeline_version="test", features_json="{}", observation_ids_json="[]", data_quality=.9)
            db.add(snapshot); db.flush()
            assessment = EdgeRiskAssessment(device_id=device_id, feature_snapshot_id=snapshot.id, hazard="flood", as_of=snapshot.as_of, probability=.2, rule_score=.1, classifier_probability=.1, anomaly_score=0, confidence=.8, risk_level="NORMAL", data_quality=.9, agreement_count=0, model_version="test", contributors_json="[]")
            db.add(assessment); db.flush()
        updated = _update_event_state(db, device, snapshot, assessment)
        assert updated.state == "RECOVERY"


def test_simulator_to_storage_features_risk_and_snapshot(client):
    response = client.post("/api/edge/simulations", json={
        "scenario": "tsunami-seismic-001", "numberOfDevices": 2, "seed": 77,
        "region": "odisha_coast", "speedMultiplier": 300, "timestepSeconds": 10,
    })
    assert response.status_code == 201
    run_id = response.json()["runId"]
    deadline = time.monotonic() + 3
    snapshot = None
    while time.monotonic() < deadline:
        snapshot = client.get("/api/edge/snapshot").json()
        run = next(item for item in snapshot["simulations"] if item["runId"] == run_id)
        if run["emittedCount"] >= 4:
            break
        time.sleep(.1)
    assert run["emittedCount"] >= 4
    run_devices = [item for item in snapshot["devices"] if run_id[:8] in item["deviceId"]]
    assert len(run_devices) == 2
    assert all(item["deviceType"] == "coastal_buoy" for item in run_devices)
    assert any(item["deviceId"] in {device["deviceId"] for device in run_devices} and item["hazard"] == "tsunami" for item in snapshot["risks"])
    stopped = client.post(f"/api/edge/simulations/{run_id}/stop")
    assert stopped.status_code == 200
    assert stopped.json()["status"] == "stopped"
    reset = client.post(f"/api/edge/simulations/{run_id}/reset")
    assert reset.status_code == 200
    assert reset.json()["runId"] != run_id
    assert reset.json()["scenario"] == "tsunami-seismic-001"
    client.post(f"/api/edge/simulations/{reset.json()['runId']}/stop")


@pytest.mark.parametrize("scenario", ["normal-operation", "flood-gradual-001", "flash-flood-001", "landslide-rain-001", "landslide-slope-001", "tsunami-seismic-001", "sensor-failure-001", "outage-recovery-001", "false-spike-001", "conflicting-sensors-001", "event-recovery-001"])
def test_scenario_generators_smoke(scenario):
    import random
    for device_type in ("river_gauge", "hillslope_station", "coastal_buoy"):
        values = _measurements(device_type, scenario, .6, 30, random.Random(7), 0)
        assert values
        assert all(value is None or isinstance(value, float | int) for value in values.values())
