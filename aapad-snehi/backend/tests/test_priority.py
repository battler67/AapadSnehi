from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.priority import compute_priority, volunteer_fit


def test_priority_is_explainable_and_rewards_urgency():
    now = datetime.now(timezone.utc)
    urgent, breakdown = compute_priority(
        severity=5,
        occurred_at=now - timedelta(hours=1),
        affected_estimate=20_000,
        needs=["food", "shelter", "medical"],
        verification_status="official",
        now=now,
    )
    old_unverified, _ = compute_priority(
        severity=2,
        occurred_at=now - timedelta(days=15),
        affected_estimate=20,
        needs=["verification"],
        verification_status="unverified",
        now=now,
    )

    assert urgent > old_unverified
    assert 0 <= urgent <= 100
    assert set(breakdown) == {"severity", "recency", "affected", "needs", "trust", "coverageGap"}


def test_volunteer_fit_prefers_relevant_nearby_service():
    strong, strong_breakdown = volunteer_fit(
        incident_needs=["medical", "shelter"],
        incident_severity=5,
        incident_latitude=30.3,
        incident_longitude=78.0,
        services=["medical", "shelter"],
        skills=["first aid"],
        availability="available",
        volunteer_latitude=30.31,
        volunteer_longitude=78.03,
    )
    weak, _ = volunteer_fit(
        incident_needs=["medical", "shelter"],
        incident_severity=5,
        incident_latitude=30.3,
        incident_longitude=78.0,
        services=["food"],
        skills=[],
        availability="limited",
        volunteer_latitude=19.0,
        volunteer_longitude=72.8,
    )

    assert strong > weak
    assert strong_breakdown["distanceKm"] < 10
