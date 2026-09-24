import json
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone, timedelta

import pytest
from sqlalchemy import select

from app.database import SessionLocal
from app.flood.auth import digest
from app.flood.models import Identity, Team, Operation


@pytest.fixture
def access(client):
    key = uuid.uuid4().hex
    with SessionLocal() as db:
        db.info["flood_access"] = True
        team = Team(id=key, name="Synthetic test team", scope="test city")
        db.add(team)
        db.flush()
        db.add_all([Identity(id=key+"c", name="Test coordinator", token_hash=digest(key+"coord"), role="coordinator", scope="test city"),
                    Identity(id=key+"r", name="Test responder", token_hash=digest(key+"resp"), role="responder", scope="test city", team_id=key),
                    Identity(id=key+"x", name="Other city", token_hash=digest(key+"other"), role="coordinator", scope="other city")])
        db.commit()
    return {"coord": {"Authorization": "Bearer "+key+"coord"}, "resp": {"Authorization": "Bearer "+key+"resp"}, "other": {"Authorization": "Bearer "+key+"other"}, "team": key}


def payload(**overrides):
    p = {"idempotency_key": str(uuid.uuid4()), "reporter_token": uuid.uuid4().hex*2, "kind": "rescue", "address": {"state": "Test state", "city": "Test city", "locality": "Locality "+uuid.uuid4().hex[:8], "street": "Canal Street", "door": "12-4/7A", "landmark": "Fictional clock", "directions": "PRIVATE ACCESS NOTE"},
         "location": {"latitude": 17.431237, "longitude": 78.492713, "source": "manual_pin", "confirmed": True, "precision": "building"},
         "observed_at": datetime.now(timezone.utc).isoformat(), "time_quality": "exact", "water_level": "knee", "people": 4, "count_quality": "estimated", "contact": "PRIVATE CONTACT", "assistance": ["limited_mobility"]}
    p.update(overrides)
    return p


def create(client, p=None):
    p = p or payload()
    r = client.post("/api/flood/reports", json=p)
    assert r.status_code == 201, r.text
    return r.json(), p


def detail(client, receipt, access):
    r = client.get(f"/api/flood/incidents/{receipt['incidentId']}?private=true", headers=access["coord"])
    assert r.status_code == 200, r.text
    return r.json()


def review(client, receipt, access, **overrides):
    d = detail(client, receipt, access)
    p = {"version": d["version"], "report_id": receipt["reportId"], "verification": "unverified", "urgency": "high", "reason": "Reviewed citizen evidence"}
    p.update(overrides)
    return client.patch(f"/api/flood/incidents/{receipt['incidentId']}/review", json=p, headers=access["coord"])


def move_task(client, receipt, access, state, **extras):
    d = detail(client, receipt, access)
    task = d["tasks"][0]
    p = {"version": task["version"], "state": state, "note": "Explicit test transition"}
    p.update(extras)
    return client.patch(f"/api/flood/tasks/{task['id']}", json=p, headers=access["coord"])


def test_private_data_and_legacy_bypass(client, access, valid_jpeg_bytes):
    r, p = create(client)
    public = client.get(f"/api/flood/incidents/{r['incidentId']}")
    assert public.status_code == 200
    for secret in ["17.431237", "78.492713", "PRIVATE", "12-4/7A", "limited_mobility", p["reporter_token"]]:
        assert secret not in public.text
    assert public.json()["point"] != [17.431237, 78.492713]
    assert public.headers["cache-control"] == "no-store"
    assert client.get(f"/api/flood/incidents/{r['incidentId']}?private=true").status_code == 401
    assert client.get(f"/api/flood/incidents/{r['incidentId']}?private=true", headers=access["other"]).status_code == 403
    legacy = client.get("/api/reports")
    assert r["reference"] not in legacy.text
    assert client.get(f"/api/reports/{r['reference']}/image").status_code == 404
    assert client.patch(f"/api/reports/{r['reference']}/moderation", json={"decision": "accepted", "reviewer_name": "test"}).status_code in {404, 422}
    upload = client.post(f"/api/flood/reports/{r['reportId']}/media", files={"image": ("photo.jpg", valid_jpeg_bytes, "image/jpeg")}, headers={"X-Reporter-Token": p["reporter_token"]})
    assert upload.status_code == 201, upload.text
    media_id = upload.json()["id"]
    assert client.get(f"/api/flood/media/{media_id}").status_code == 403
    assert client.get(f"/api/flood/media/{media_id}", headers=access["coord"]).status_code == 200
    assert client.get(f"/api/flood/media/{media_id}", headers=access["resp"]).status_code == 403


def test_retry_and_failed_media(client, access):
    r, p = create(client)
    retry = client.post("/api/flood/reports", json=p)
    assert retry.json()["reportId"] == r["reportId"] and retry.json()["duplicateRetry"]
    assert client.post("/api/flood/reports", json={**p, "people": 9}).status_code == 409
    bad = client.post(f"/api/flood/reports/{r['reportId']}/media", files={"image": ("fake.jpg", b"not an image", "image/jpeg")}, headers={"X-Reporter-Token": p["reporter_token"]})
    assert bad.status_code == 422
    assert detail(client, r, access)["reportCount"] == 1


def test_ambiguous_location_and_observation_staleness(client, access):
    r, p = create(client, payload(location={"source": "text"}, observed_at=(datetime.now(timezone.utc)-timedelta(days=2)).isoformat()))
    d = detail(client, r, access)
    assert d["point"] is None and d["stale"] and d["locationStatus"] == "clarification"
    assert review(client, r, access).status_code == 200
    assert detail(client, r, access)["stale"]
    summary = client.get("/api/flood/incidents", params={"locality": p["address"]["locality"]}).json()["summary"]
    assert summary["unresolvedLocationReports"] == 1


def test_repeated_counts_and_street_identity(client, access):
    r, p = create(client)
    update = {**p, "idempotency_key": str(uuid.uuid4()), "kind": "update", "update_incident_id": r["incidentId"]}
    second, _ = create(client, update)
    assert review(client, second, access).status_code == 200
    params = {"private": "true", "locality": p["address"]["locality"]}
    s = client.get("/api/flood/incidents", params=params, headers=access["coord"]).json()["summary"]
    assert s["estimatedPeople"] == 4 and s["buildingsReportingFlooding"] == 1
    different = {**p, "idempotency_key": str(uuid.uuid4()), "address": {**p["address"], "street": "Different Street"}}
    third, _ = create(client, different)
    assert review(client, third, access).status_code == 200
    s = client.get("/api/flood/incidents", params=params, headers=access["coord"]).json()["summary"]
    assert s["estimatedPeople"] == 8 and s["buildingsReportingFlooding"] == 2
    duplicate, _ = create(client, {**p, "idempotency_key": str(uuid.uuid4())})
    assert review(client, duplicate, access).status_code == 200
    s = client.get("/api/flood/incidents", params=params, headers=access["coord"]).json()["summary"]
    assert s["estimatedPeople"] == 4 and s["unknownOrUnreviewedCounts"] == 1


def test_permissions_state_machine_and_resolution(client, access):
    r, _ = create(client)
    d = detail(client, r, access)
    body = {"version": d["version"], "report_id": r["reportId"], "verification": "unverified", "urgency": "high", "reason": "review test"}
    assert client.patch(f"/api/flood/incidents/{r['incidentId']}/review", json=body).status_code == 401
    assert client.patch(f"/api/flood/incidents/{r['incidentId']}/review", json=body, headers=access["resp"]).status_code == 403
    assert move_task(client, r, access, "assigned", team_id=access["team"]).status_code == 422
    assert review(client, r, access).status_code == 200
    for state in ["ready", "assigned", "en_route", "on_scene"]:
        result = move_task(client, r, access, state, **({"team_id": access["team"]} if state == "assigned" else {}))
        assert result.status_code == 200, result.text
    assert client.get(f"/api/flood/incidents/{r['incidentId']}?private=true", headers=access["resp"]).status_code == 200
    assert move_task(client, r, access, "resolved", outcome="Assisted to staging point", assisted=4, remaining="none").status_code == 200
    assert detail(client, r, access)["status"] == "active"
    assert move_task(client, r, access, "needs_review").status_code == 200


def test_concurrent_assignments(client, access):
    r, _ = create(client)
    assert review(client, r, access).status_code == 200
    assert move_task(client, r, access, "ready").status_code == 200
    task = detail(client, r, access)["tasks"][0]
    p = {"version": task["version"], "state": "assigned", "team_id": access["team"], "note": "Concurrent assignment"}
    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = list(pool.map(lambda _: client.patch(f"/api/flood/tasks/{task['id']}", json=p, headers=access["coord"]), range(2)))
    assert sorted(x.status_code for x in responses) == [200, 409]


def test_merge_retains_reports_tasks_and_history(client, access):
    a, _ = create(client)
    b, _ = create(client)
    def merge():
        left, right = detail(client, a, access), detail(client, b, access)
        return client.post(f"/api/flood/incidents/{a['incidentId']}/merge", json={"version": left["version"], "target_version": right["version"], "target_incident_id": b["incidentId"], "reason": "Reviewed duplicate reports", "acknowledge_tasks": True}, headers=access["coord"])
    assert merge().status_code == 409
    assert move_task(client, a, access, "cancelled", outcome="Duplicate").status_code == 200
    assert merge().status_code == 200
    d = detail(client, b, access)
    assert d["reportCount"] == 2 and len(d["tasks"]) == 2
    assert any(e["action"] == "incident_merge_received" for e in d["timeline"])
    assert any(e["action"] == "citizen_observation" for e in detail(client, a, access)["timeline"])


def test_conflicting_counts_require_review_and_independent_reporters(client, access):
    r, p = create(client)
    second, _ = create(client, {**p, "idempotency_key": str(uuid.uuid4()), "kind": "update", "update_incident_id": r["incidentId"], "people": 9})
    d = detail(client, r, access)
    assert d["conflict"] and d["reportedPeople"] is None
    assert review(client, second, access, verification="corroborated").status_code == 422
    assert review(client, r, access).status_code == 200
    d = detail(client, r, access)
    assert d["reportedPeople"] == 4 and d["conflict"]


def test_media_derivative_strips_metadata_and_retry_is_one_photo(client, access):
    import io
    from PIL import Image
    r, p = create(client)
    output = io.BytesIO()
    image = Image.new("RGB", (40, 40), "blue")
    exif = Image.Exif()
    exif[270] = "PRIVATE HOUSE LOCATION"
    image.save(output, format="JPEG", exif=exif)
    headers = {"X-Reporter-Token": p["reporter_token"]}
    ids = []
    for _ in range(2):
        result = client.post(f"/api/flood/reports/{r['reportId']}/media", files={"image": ("evidence.jpg", output.getvalue(), "image/jpeg")}, headers=headers)
        assert result.status_code == 201
        ids.append(result.json()["id"])
    assert ids[0] == ids[1]
    derivative = client.get(f"/api/flood/media/{ids[0]}", headers=access["coord"])
    assert b"PRIVATE HOUSE LOCATION" not in derivative.content
    assert not Image.open(io.BytesIO(derivative.content)).getexif()
    assert client.get(f"/api/flood/media/{ids[0]}?original=true").status_code == 403


def test_receipt_lookup_and_location_correction_audited(client, access):
    r, p = create(client)
    assert client.get("/api/flood/receipt", params={"reference": r["reference"]}).status_code == 403
    assert client.get("/api/flood/receipt", params={"reference": r["reference"]}, headers={"X-Reporter-Token": p["reporter_token"]}).json()["reportId"] == r["reportId"]
    d = detail(client, r, access)
    result = client.patch(f"/api/flood/reports/{r['reportId']}/location", json={"version": d["version"], "location": {"latitude": 18, "longitude": 79, "source": "manual_pin", "confirmed": True, "precision": "street"}, "reason": "Reporter corrected GPS point"}, headers={"X-Reporter-Token": p["reporter_token"]})
    assert result.status_code == 200
    updated = detail(client, r, access)
    assert updated["point"] == [18, 79]
    assert updated["lastObservation"] == d["lastObservation"]
    assert updated["timeline"][-1]["action"] == "location_confirmed"
    assert client.get("/api/flood/geocode?q=test").status_code == 503


def test_inaccurate_gps_cannot_be_building_precision(client):
    p = payload(location={"latitude": 17, "longitude": 78, "source": "device_gps", "accuracy": 200, "confirmed": True, "precision": "building"})
    assert client.post("/api/flood/reports", json=p).status_code == 422
    p["location"]["precision"] = "locality"
    assert client.post("/api/flood/reports", json=p).status_code == 201


def test_regroup_preserves_retained_task_and_history(client, access):
    r, _ = create(client)
    d = detail(client, r, access)
    result = client.post(f"/api/flood/reports/{r['reportId']}/regroup", json={"version": d["version"], "reason": "Separate household after review"}, headers=access["coord"])
    assert result.status_code == 200, result.text
    old = detail(client, r, access)
    assert not old["reports"] and len(old["tasks"]) == 1 and old["timeline"]
    assert "Existing assignments remain" in result.json()["taskPolicy"]


def test_coordinate_migration_preserves_rows_indexes_and_backup(tmp_path):
    from sqlalchemy import create_engine, inspect, text
    from app.flood.migration import migrate_coordinates
    engine = create_engine(f"sqlite:///{tmp_path / 'legacy.db'}")
    with engine.begin() as conn:
        conn.execute(text("CREATE TABLE incidents (id INTEGER PRIMARY KEY, latitude FLOAT NOT NULL, longitude FLOAT NOT NULL, title TEXT NOT NULL)"))
        conn.execute(text("CREATE INDEX ix_test_lat ON incidents(latitude)"))
        conn.execute(text("INSERT INTO incidents VALUES (1, 17, 78, 'Keep existing record')"))
    migrate_coordinates(engine)
    migrate_coordinates(engine)
    with engine.begin() as conn:
        assert conn.scalar(text("SELECT title FROM incidents WHERE id=1")) == "Keep existing record"
        conn.execute(text("INSERT INTO incidents VALUES (2, NULL, NULL, 'Unknown point')"))
    assert any(i["name"] == "ix_test_lat" for i in inspect(engine).get_indexes("incidents"))
    assert (tmp_path / "legacy.before-flood.sqlite").exists()
    engine.dispose()


def test_coordinator_can_create_rescue_task_for_flood_observation(client, access):
    r, _ = create(client, payload(kind="flood", people=None, count_quality="unknown"))
    d = detail(client, r, access)
    assert not d["tasks"]
    body = {"version": d["version"], "reason": "Reviewed request for assistance"}
    assert client.post(f"/api/flood/incidents/{r['incidentId']}/task", json=body).status_code == 401
    response = client.post(f"/api/flood/incidents/{r['incidentId']}/task", json=body, headers=access["coord"])
    assert response.status_code == 201 and response.json()["state"] == "needs_review"
    body["version"] = detail(client, r, access)["version"]
    assert client.post(f"/api/flood/incidents/{r['incidentId']}/task", json=body, headers=access["coord"]).status_code == 409


def test_named_building_has_multiple_units_without_inflating_buildings(client, access):
    p = payload()
    p["address"].update(building="Lotus Apartments", door="Unit 1")
    first, _ = create(client, p)
    second, _ = create(client, {**p, "idempotency_key": str(uuid.uuid4()), "address": {**p["address"], "door": "Unit 2"}})
    assert review(client, first, access).status_code == 200
    assert review(client, second, access).status_code == 200
    response = client.get("/api/flood/incidents", params={"private": "true", "locality": p["address"]["locality"], "group_by": "building"}, headers=access["coord"])
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["summary"]["buildingsReportingFlooding"] == 1
    assert data["summary"]["estimatedPeople"] == 8
    assert len(data["groups"]) == 1
