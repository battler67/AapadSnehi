from __future__ import annotations

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import uuid
import pytest

from app.allocation import (
    AllocationProblem,
    IncidentAllocationInput,
    VolunteerAllocationInput,
    get_strategy,
    strategy_metadata,
)
from app.allocation.capacity import CapacityCandidate



def test_balanced_greedy_allocates_by_proximity_and_service_match():
    problem = AllocationProblem(
        incidents=(
            IncidentAllocationInput(
                id=10,
                title="Food emergency",
                location_name="Guwahati",
                severity=4,
                priority_score=75.0,
                latitude=26.14,
                longitude=91.73,
                needs=("food", "shelter"),
                existing_coverage=0,
            ),
            IncidentAllocationInput(
                id=20,
                title="Medical emergency",
                location_name="Nagaon",
                severity=5,
                priority_score=90.0,
                latitude=26.35,
                longitude=92.68,
                needs=("medical",),
                existing_coverage=0,
            ),
        ),
        volunteers=(
            VolunteerAllocationInput(
                id=101,
                name="Food Specialist",
                availability="available",
                latitude=26.15,
                longitude=91.74,
                services=("food",),
                skills=("cooking",),
            ),
            VolunteerAllocationInput(
                id=102,
                name="Medic Volunteer",
                availability="available",
                latitude=26.34,
                longitude=92.67,
                services=("medical",),
                skills=("first-aid",),
            ),
        ),
    )
    strategy = get_strategy("balanced-greedy-v1")
    plan = strategy.allocate(problem)

    assert len(plan.decisions) == 2
    assert len(plan.unassigned) == 0


    decisions = {d.volunteer_id: d for d in plan.decisions}
    assert decisions[101].incident_id == 10
    assert decisions[101].service == "food"
    assert decisions[102].incident_id == 20
    assert decisions[102].service == "medical"


def test_allocation_skips_busy_or_duplicate_volunteers():
    problem = AllocationProblem(
        incidents=(
            IncidentAllocationInput(
                id=10,
                title="Medical emergency",
                location_name="Guwahati",
                severity=5,
                priority_score=80.0,
                latitude=26.14,
                longitude=91.73,
                needs=("medical",),
                existing_coverage=0,
            ),
        ),
        volunteers=(
            VolunteerAllocationInput(
                id=101,
                name="Busy Medic",
                availability="unavailable",
                latitude=26.14,
                longitude=91.73,
                services=("medical",),
                skills=(),
            ),
            VolunteerAllocationInput(
                id=102,
                name="Already Assigned Medic",
                availability="available",
                latitude=26.14,
                longitude=91.73,
                services=("medical",),
                skills=(),
            ),
        ),
        existing_pairs=frozenset([(10, 102)]),
    )
    strategy = get_strategy("balanced-greedy-v1")
    plan = strategy.allocate(problem)

    assert len(plan.decisions) == 0
    assert len(plan.unassigned) == 2



def test_allocation_registry_exposes_replaceable_strategy_metadata():
    metadata = strategy_metadata()
    assert [item["key"] for item in metadata] == [
        "balanced-greedy-v1",
        "global-optimal-v1",
        "stable-matching-v1",
    ]
    assert all(item["summary"] and item["bestFor"] for item in metadata)


def _two_by_two_problem() -> AllocationProblem:
    return AllocationProblem(
        incidents=(
            IncidentAllocationInput(10, "A", "A", 1, 10, 0, 0, ("rescue",)),
            IncidentAllocationInput(20, "B", "B", 1, 10, 0, 0, ("rescue",)),
        ),
        volunteers=(
            VolunteerAllocationInput(101, "One", "available", 0, 0, ("rescue",), ()),
            VolunteerAllocationInput(102, "Two", "available", 0, 0, ("rescue",), ()),
        ),
    )


def test_global_optimal_strategy_maximizes_the_complete_plan(monkeypatch):
    from app.allocation import global_optimal

    scores = {(101, 10): 100.0, (101, 20): 99.0, (102, 10): 98.0, (102, 20): 1.0}

    def scored(incident, volunteer, *, slot_index):
        score = scores[(volunteer.id, incident.id)]
        return CapacityCandidate(incident, volunteer, "rescue", score, score, {"test": score})

    monkeypatch.setattr(global_optimal, "capacity_candidate", scored)
    plan = get_strategy("global-optimal-v1").allocate(_two_by_two_problem())
    assert {(item.volunteer_id, item.incident_id) for item in plan.decisions} == {
        (101, 20),
        (102, 10),
    }
    assert sum(item.allocation_score for item in plan.decisions) == 197.0


def test_stable_matching_rejects_a_blocking_pair(monkeypatch):
    from app.allocation import stable_matching

    # Both volunteers propose to A first. A retains volunteer 102 because its
    # incident-side fit is stronger, so 101 continues to B.
    scores = {
        (101, 10): (10.0, 100.0),
        (101, 20): (100.0, 90.0),
        (102, 10): (100.0, 80.0),
        (102, 20): (10.0, 70.0),
    }

    def scored(incident, volunteer, *, slot_index):
        fit, allocation = scores[(volunteer.id, incident.id)]
        return CapacityCandidate(
            incident,
            volunteer,
            "rescue",
            fit,
            allocation,
            {"test": allocation},
        )

    monkeypatch.setattr(stable_matching, "capacity_candidate", scored)
    plan = get_strategy("stable-matching-v1").allocate(_two_by_two_problem())
    assert {(item.volunteer_id, item.incident_id) for item in plan.decisions} == {
        (101, 20),
        (102, 10),
    }


def test_capacity_strategies_are_deterministic_and_respect_slot_limits():
    incident = IncidentAllocationInput(
        10, "One-slot incident", "A", 1, 10, 0, 0, ("food",)
    )
    problem = AllocationProblem(
        incidents=(incident,),
        volunteers=(
            VolunteerAllocationInput(101, "Near", "available", 0, 0, ("food",), ()),
            VolunteerAllocationInput(102, "Far", "available", 10, 10, ("food",), ()),
            VolunteerAllocationInput(103, "Busy", "unavailable", 0, 0, ("food",), ()),
        ),
    )
    for key in ("global-optimal-v1", "stable-matching-v1"):
        first = get_strategy(key).allocate(problem)
        second = get_strategy(key).allocate(problem)
        assert first == second
        assert [item.volunteer_id for item in first.decisions] == [101]
        assert {item.volunteer_id for item in first.unassigned} == {102, 103}


def _register_volunteer(client, *, name: str, service: str, latitude: float, longitude: float):
    response = client.post(
        "/api/volunteers",
        json={
            "name": name,
            "phone": f"+91-{uuid.uuid4().hex[:10]}",
            "email": f"{uuid.uuid4().hex[:8]}@example.org",
            "home_location": "Allocation test base",
            "preferred_places": ["Allocation test district"],
            "latitude": latitude,
            "longitude": longitude,
            "services": [service],
            "skills": [],
            "languages": ["hindi"],
            "availability": "available",
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


@pytest.mark.parametrize(
    "strategy_key",
    ["balanced-greedy-v1", "global-optimal-v1", "stable-matching-v1"],
)
def test_distribution_api_previews_then_commits_atomically(client, strategy_key):
    incidents = client.get("/api/tasks/open").json()
    food_incident = next(item for item in incidents if "food" in item["needs"])
    rescue_incident = next(item for item in incidents if "rescue" in item["needs"])
    food_volunteer = _register_volunteer(
        client,
        name="Batch Food Volunteer",
        service="food",
        latitude=food_incident["latitude"],
        longitude=food_incident["longitude"],
    )
    rescue_volunteer = _register_volunteer(
        client,
        name="Batch Rescue Volunteer",
        service="rescue",
        latitude=rescue_incident["latitude"],
        longitude=rescue_incident["longitude"],
    )
    before = len(client.get("/api/assignments").json())
    request = {
        "incident_ids": [food_incident["id"], rescue_incident["id"]],
        "volunteer_ids": [food_volunteer["id"], rescue_volunteer["id"]],
        "strategy": strategy_key,
        "note": "Automated allocation API test",
    }

    preview = client.post("/api/allocations/distribute", json={**request, "commit": False})
    assert preview.status_code == 200, preview.text
    assert preview.json()["committed"] is False
    assert preview.json()["summary"]["allocatedVolunteers"] == 2
    assert len(client.get("/api/assignments").json()) == before

    committed = client.post(
        "/api/allocations/distribute",
        json={
            **request,
            "commit": True,
            "preview_token": preview.json()["previewToken"],
        },
    )
    assert committed.status_code == 200, committed.text
    payload = committed.json()
    assert payload["committed"] is True
    assert len(payload["assignments"]) == 2
    assert all(
        item["assignedBy"] == f"Automated distribution: {strategy_key}"
        for item in payload["assignments"]
    )
    assert len(client.get("/api/assignments").json()) == before + 2
    volunteer_states = {
        item["id"]: item["availability"] for item in client.get("/api/volunteers").json()
    }
    assert volunteer_states[food_volunteer["id"]] == "limited"
    assert volunteer_states[rescue_volunteer["id"]] == "limited"


def test_distribution_commit_requires_matching_preview(client):
    response = client.post(
        "/api/allocations/distribute",
        json={
            "incident_ids": [1],
            "volunteer_ids": [1],
            "strategy": "balanced-greedy-v1",
            "commit": True,
            "preview_token": "stale-preview",
        },
    )
    assert response.status_code == 409
    assert "changed after preview" in response.json()["detail"]


def test_distribution_api_rejects_unknown_strategy(client):
    response = client.post(
        "/api/allocations/distribute",
        json={
            "incident_ids": [1],
            "volunteer_ids": [1],
            "strategy": "not-installed",
            "commit": False,
        },
    )
    assert response.status_code == 422
    assert "Unknown allocation strategy" in response.json()["detail"]
