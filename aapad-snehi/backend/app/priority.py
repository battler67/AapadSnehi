from __future__ import annotations

import math
from datetime import datetime, timezone


TRUST_SCORES = {
    "official": 10.0,
    "corroborated": 7.0,
    "community_reviewed": 5.0,
    "ai_screened": 3.0,
    "unverified": 2.0,
}


def ensure_aware(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def compute_priority(
    *,
    severity: int,
    occurred_at: datetime,
    affected_estimate: int,
    needs: list[str],
    verification_status: str,
    response_coverage: int = 0,
    now: datetime | None = None,
) -> tuple[float, dict[str, float]]:
    """Return an explainable 0-100 response-priority score.

    The formula is deliberately deterministic. It is an operational recommendation,
    not a scientific estimate of human harm.
    """

    reference = ensure_aware(now or datetime.now(timezone.utc))
    age_hours = max(0.0, (reference - ensure_aware(occurred_at)).total_seconds() / 3600)
    severity_points = min(40.0, max(0.0, severity / 5 * 40))
    recency_points = 20.0 * math.exp(-age_hours / 72.0)
    affected_points = min(15.0, math.log10(max(1, affected_estimate) + 1) / 5 * 15)
    needs_points = min(10.0, len(set(needs)) * 2.5)
    trust_points = TRUST_SCORES.get(verification_status, 1.0)
    coverage_points = max(0.0, 5.0 - min(5.0, response_coverage * 1.5))
    breakdown = {
        "severity": round(severity_points, 1),
        "recency": round(recency_points, 1),
        "affected": round(affected_points, 1),
        "needs": round(needs_points, 1),
        "trust": round(trust_points, 1),
        "coverageGap": round(coverage_points, 1),
    }
    return round(min(100.0, sum(breakdown.values())), 1), breakdown


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    radius_km = 6371.0
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lon2 - lon1)
    a = (
        math.sin(delta_phi / 2) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda / 2) ** 2
    )
    return radius_km * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def volunteer_fit(
    *,
    incident_needs: list[str],
    incident_severity: int,
    incident_latitude: float,
    incident_longitude: float,
    services: list[str],
    skills: list[str],
    availability: str,
    volunteer_latitude: float,
    volunteer_longitude: float,
) -> tuple[float, dict[str, float]]:
    distance = haversine_km(
        incident_latitude,
        incident_longitude,
        volunteer_latitude,
        volunteer_longitude,
    )
    capability_set = {item.lower() for item in services + skills}
    need_set = {item.lower() for item in incident_needs}
    overlap = len(capability_set & need_set)
    skill_points = min(45.0, overlap * 18.0 + (8.0 if capability_set else 0.0))
    distance_points = max(0.0, 30.0 - min(30.0, distance / 20.0))
    availability_points = 15.0 if availability == "available" else 5.0 if availability == "limited" else 0.0
    urgency_points = incident_severity / 5 * 10.0
    breakdown = {
        "capability": round(skill_points, 1),
        "distance": round(distance_points, 1),
        "availability": round(availability_points, 1),
        "urgency": round(urgency_points, 1),
    }
    return round(sum(breakdown.values()), 1), {**breakdown, "distanceKm": round(distance, 1)}
