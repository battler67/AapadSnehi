from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol


@dataclass(frozen=True)
class IncidentAllocationInput:
    id: int
    title: str
    location_name: str
    severity: int
    priority_score: float
    latitude: float
    longitude: float
    needs: tuple[str, ...]
    existing_coverage: int = 0


@dataclass(frozen=True)
class VolunteerAllocationInput:
    id: int
    name: str
    availability: str
    latitude: float
    longitude: float
    services: tuple[str, ...]
    skills: tuple[str, ...]


@dataclass(frozen=True)
class AllocationProblem:
    incidents: tuple[IncidentAllocationInput, ...]
    volunteers: tuple[VolunteerAllocationInput, ...]
    existing_pairs: frozenset[tuple[int, int]] = field(default_factory=frozenset)


@dataclass(frozen=True)
class AllocationDecision:
    incident_id: int
    incident_title: str
    incident_location: str
    volunteer_id: int
    volunteer_name: str
    service: str
    fit_score: float
    allocation_score: float
    breakdown: dict[str, float]


@dataclass(frozen=True)
class UnassignedVolunteer:
    volunteer_id: int
    volunteer_name: str
    reason: str


@dataclass(frozen=True)
class AllocationPlan:
    strategy_key: str
    strategy_name: str
    strategy_version: str
    decisions: tuple[AllocationDecision, ...]
    unassigned: tuple[UnassignedVolunteer, ...]


class AllocationStrategy(Protocol):
    """Stable extension contract for volunteer-distribution algorithms."""

    key: str
    name: str
    version: str

    def allocate(self, problem: AllocationProblem) -> AllocationPlan:
        """Return a deterministic proposal without mutating application state."""

        ...
