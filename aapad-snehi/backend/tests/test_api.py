from __future__ import annotations

import uuid


def test_quick_demo_exposes_no_portal_auth_routes(client):
    schema = client.get("/openapi.json").json()

    assert not any(path.startswith("/api/auth") for path in schema["paths"])
    assert all(
        not operation.get("security")
        for path in schema["paths"].values()
        for operation in path.values()
        if isinstance(operation, dict)
    )


def test_dashboard_and_time_filtered_heatmap(client):
    dashboard = client.get("/api/dashboard")
    assert dashboard.status_code == 200
    assert dashboard.json()["metrics"]["activeIncidents"] >= 7

    heatmap = client.get("/api/incidents/heatmap?days=30")
    assert heatmap.status_code == 200
    assert heatmap.json()
    assert all(0 < point["weight"] <= 1 for point in heatmap.json())

    preflight = client.options(
        "/api/dashboard",
        headers={
            "Origin": "http://127.0.0.1:5173",
            "Access-Control-Request-Method": "GET",
        },
    )
    assert preflight.status_code == 200


def test_demo_has_a_large_seeded_volunteer_pool(client):
    response = client.get("/api/volunteers")

    assert response.status_code == 200
    volunteers = response.json()
    assert len(volunteers) >= 12
    assert {
        "+91 90000 11005",
        "+91 90000 11008",
        "+91 90000 11012",
    }.issubset({volunteer["phone"] for volunteer in volunteers})


def test_citizen_report_is_unverified_and_tracks_evidence(client, valid_jpeg_bytes):
    response = client.post(
        "/api/reports",
        data={
            "description": "Flood water has entered homes and food support is needed.",
            "disaster_type": "flood",
            "severity": "4",
            "latitude": "26.14",
            "longitude": "91.73",
            "location_name": "Guwahati, Assam",
            "needs": '["food", "shelter"]',
            "reporter_name": "Test reporter",
            "contact": "+91 90000 00000",
            "consent": "true",
        },
        files={"image": ("evidence.jpg", valid_jpeg_bytes, "image/jpeg")},
    )
    assert response.status_code == 201, response.text
    payload = response.json()
    assert payload["trackingId"].startswith("AS-")
    assert payload["incident"]["verificationStatus"] == "unverified"
    assert payload["moderationStatus"] == "needs_volunteer_review"
    assert payload["incident"]["active"] is False


def test_volunteer_registration_and_demo_assignment(client):
    phone = f"+91-{uuid.uuid4().hex[:10]}"
    created = client.post(
        "/api/volunteers",
        json={
            "name": "Test Volunteer",
            "phone": phone,
            "email": "volunteer@example.org",
            "home_location": "Guwahati, Assam",
            "preferred_places": [
                "  Guwahati,   Assam ",
                "guwahati, assam",
                "Nagaon, Assam",
            ],
            "latitude": 26.1445,
            "longitude": 91.7362,
            "services": ["food", "shelter"],
            "skills": ["logistics"],
            "languages": ["hindi"],
            "availability": "available",
        },
    )
    assert created.status_code == 201, created.text

    created_payload = created.json()
    assert created_payload["preferredPlaces"] == ["Guwahati, Assam", "Nagaon, Assam"]
    volunteer_id = created_payload["id"]
    incident_id = client.get("/api/tasks/open").json()[0]["id"]

    suggestions = client.get(f"/api/incidents/{incident_id}/suggestions")
    assert suggestions.status_code == 200
    assert any(item["id"] == volunteer_id for item in suggestions.json())

    assignment = client.post(
        "/api/assignments",
        json={
            "incident_id": incident_id,
            "volunteer_id": volunteer_id,
            "service": "food",
            "note": "Bring packaged meals to the coordination point.",
        },
    )
    assert assignment.status_code == 201, assignment.text
    assert assignment.json()["status"] == "assigned"


def test_volunteer_preferred_places_are_required_and_limited(client):
    base_payload = {
        "name": "Preference Validation Volunteer",
        "phone": f"+91-{uuid.uuid4().hex[:10]}",
        "email": "preference-validation@example.org",
        "home_location": "Pune, Maharashtra",
        "latitude": 18.5204,
        "longitude": 73.8567,
        "services": ["food"],
        "skills": [],
        "languages": ["marathi"],
        "availability": "available",
    }

    missing = client.post("/api/volunteers", json=base_payload)
    assert missing.status_code == 422

    too_many = client.post(
        "/api/volunteers",
        json={
            **base_payload,
            "preferred_places": ["Pune", "Mumbai", "Nashik", "Nagpur", "Satara", "Kolhapur"],
        },
    )
    assert too_many.status_code == 422


def test_seeded_volunteers_have_preferred_work_areas(client):
    response = client.get("/api/volunteers")
    assert response.status_code == 200
    assert response.json()
    assert all(volunteer["preferredPlaces"] for volunteer in response.json())


def test_demo_ingestion_is_idempotent_and_live_is_gated(client):
    demo = client.post("/api/ingestion/run", json={"source_ids": [], "live": False})
    assert demo.status_code == 200
    statuses = {run["status"] for run in demo.json()}
    assert "success" in statuses
    assert "skipped" in statuses

    live = client.post("/api/ingestion/run", json={"source_ids": [], "live": True})
    assert live.status_code == 403
