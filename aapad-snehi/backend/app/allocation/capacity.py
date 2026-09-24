from __future__ import annotations

import math
from dataclasses import dataclass

from ..priority import volunteer_fit
from .base import (
    AllocationDecision,
    AllocationProblem,
    IncidentAllocationInput,
    UnassignedVolunteer,
    VolunteerAllocationInput,
)


@dataclass(frozen=True)
class CapacityCandidate:
    incident: IncidentAllocationInput
    volunteer: VolunteerAllocationInput
    service: str
    fit_score: float
    allocation_score: float
    breakdown: dict[str, float]


def matching_services(
    incident: IncidentAllocationInput,
    volunteer: VolunteerAllocationInput,
) -> tuple[str, ...]:
    registered = {service.casefold() for service in volunteer.services}
    return tuple(need for need in incident.needs if need.casefold() in registered)


def target_coverage(incident: IncidentAllocationInput) -> int:
    """Return a bounded experimental response-slot target, not a staffing rule."""

    return min(
        5,
        max(
            1,
            len(set(incident.needs)),
            math.ceil(incident.severity / 2),
            math.ceil(incident.priority_score / 25),
        ),
    )


def open_capacity(incident: IncidentAllocationInput) -> int:
    return max(0, target_coverage(incident) - incident.existing_coverage)


def capacity_candidate(
    incident: IncidentAllocationInput,
    volunteer: VolunteerAllocationInput,
    *,
    slot_index: int,
) -> CapacityCandidate | None:
    services = matching_services(incident, volunteer)
    if not services:
        return None
    fit_score, fit_breakdown = volunteer_fit(
        incident_needs=list(incident.needs),
        incident_severity=incident.severity,
        incident_latitude=incident.latitude,
        incident_longitude=incident.longitude,
        services=list(volunteer.services),
        skills=list(volunteer.skills),
        availability=volunteer.availability,
        volunteer_latitude=volunteer.latitude,
        volunteer_longitude=volunteer.longitude,
    )
    priority_contribution = incident.priority_score * 0.1
    first_coverage_bonus = (
        12.0 if incident.existing_coverage == 0 and slot_index == 0 else 0.0
    )
    slot_penalty = slot_index * 4.0
    score = round(
        fit_score + priority_contribution + first_coverage_bonus - slot_penalty,
        1,
    )
    return CapacityCandidate(
        incident=incident,
        volunteer=volunteer,
        service=services[0],
        fit_score=fit_score,
        allocation_score=score,
        breakdown={
            **fit_breakdown,
            "priorityContribution": round(priority_contribution, 1),
            "firstCoverageBonus": round(first_coverage_bonus, 1),
            "slotPenalty": round(slot_penalty, 1),
            "targetCoverage": float(target_coverage(incident)),
            "slotNumber": float(slot_index + 1),
        },
    )


def available_volunteers(
    problem: AllocationProblem,
) -> tuple[list[VolunteerAllocationInput], list[UnassignedVolunteer]]:
    available: list[VolunteerAllocationInput] = []
    unassigned: list[UnassignedVolunteer] = []
    for volunteer in sorted(problem.volunteers, key=lambda item: item.id):
        if volunteer.availability == "available":
            available.append(volunteer)
        else:
            unassigned.append(
                UnassignedVolunteer(
                    volunteer_id=volunteer.id,
                    volunteer_name=volunteer.name,
                    reason="Volunteer is not currently available",
                )
            )
    return available, unassigned


def unassigned_reason(
    problem: AllocationProblem,
    volunteer: VolunteerAllocationInput,
) -> str:
    compatible = [
        incident
        for incident in problem.incidents
        if matching_services(incident, volunteer)
    ]
    if not compatible:
        return "No selected incident requests a registered volunteer service"
    if all((incident.id, volunteer.id) in problem.existing_pairs for incident in compatible):
        return "Volunteer is already assigned to every compatible selected incident"
    if all(open_capacity(incident) == 0 for incident in compatible):
        return "Compatible incidents already meet this strategy's response-slot target"
    return "No compatible response slot remained after the strategy resolved the full plan"


def decision(candidate: CapacityCandidate) -> AllocationDecision:
    return AllocationDecision(
        incident_id=candidate.incident.id,
        incident_title=candidate.incident.title,
        incident_location=candidate.incident.location_name,
        volunteer_id=candidate.volunteer.id,
        volunteer_name=candidate.volunteer.name,
        service=candidate.service,
        fit_score=candidate.fit_score,
        allocation_score=candidate.allocation_score,
        breakdown=candidate.breakdown,
    )
