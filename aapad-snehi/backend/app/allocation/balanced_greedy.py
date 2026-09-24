from __future__ import annotations

from dataclasses import dataclass

from ..priority import volunteer_fit
from .base import (
    AllocationDecision,
    AllocationPlan,
    AllocationProblem,
    IncidentAllocationInput,
    UnassignedVolunteer,
    VolunteerAllocationInput,
)


@dataclass(frozen=True)
class _Candidate:
    incident: IncidentAllocationInput
    volunteer: VolunteerAllocationInput
    service: str
    fit_score: float
    allocation_score: float
    breakdown: dict[str, float]


class BalancedGreedyStrategy:
    key = "balanced-greedy-v1"
    name = "Balanced greedy distribution"
    version = "1.0.0"
    summary = "Repeatedly selects the strongest current pair while penalizing concentrated coverage."
    best_for = "Best for a fast, transparent plan that spreads initial coverage across selected incidents."

    @staticmethod
    def _matching_services(
        incident: IncidentAllocationInput,
        volunteer: VolunteerAllocationInput,
    ) -> list[str]:
        registered = {service.casefold() for service in volunteer.services}
        return [need for need in incident.needs if need.casefold() in registered]

    @staticmethod
    def _demand_weight(incident: IncidentAllocationInput) -> float:
        return max(
            0.5,
            incident.priority_score / 100.0
            + incident.severity / 5.0
            + min(1.0, len(incident.needs) / 5.0),
        )

    def _candidate(
        self,
        incident: IncidentAllocationInput,
        volunteer: VolunteerAllocationInput,
        planned_count: int,
    ) -> _Candidate | None:
        matching_services = self._matching_services(incident, volunteer)
        if not matching_services:
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
        effective_load = incident.existing_coverage + planned_count
        coverage_bonus = 18.0 if effective_load == 0 else 0.0
        priority_contribution = incident.priority_score * 0.1
        load_penalty = 12.0 * effective_load / self._demand_weight(incident)
        allocation_score = round(
            fit_score + coverage_bonus + priority_contribution - load_penalty,
            1,
        )
        return _Candidate(
            incident=incident,
            volunteer=volunteer,
            service=matching_services[0],
            fit_score=fit_score,
            allocation_score=allocation_score,
            breakdown={
                **fit_breakdown,
                "coverageBonus": round(coverage_bonus, 1),
                "priorityContribution": round(priority_contribution, 1),
                "loadPenalty": round(load_penalty, 1),
            },
        )

    def allocate(self, problem: AllocationProblem) -> AllocationPlan:
        planned_counts = {incident.id: 0 for incident in problem.incidents}
        remaining: dict[int, VolunteerAllocationInput] = {}
        unassigned: list[UnassignedVolunteer] = []
        for volunteer in problem.volunteers:
            if volunteer.availability != "available":
                unassigned.append(
                    UnassignedVolunteer(
                        volunteer_id=volunteer.id,
                        volunteer_name=volunteer.name,
                        reason="Volunteer is not currently available",
                    )
                )
            else:
                remaining[volunteer.id] = volunteer

        decisions: list[AllocationDecision] = []
        while remaining:
            coverable_uncovered_ids = {
                incident.id
                for incident in problem.incidents
                if incident.existing_coverage + planned_counts[incident.id] == 0
                and any(
                    (incident.id, volunteer.id) not in problem.existing_pairs
                    and self._matching_services(incident, volunteer)
                    for volunteer in remaining.values()
                )
            }
            candidate_incidents = (
                tuple(
                    incident
                    for incident in problem.incidents
                    if incident.id in coverable_uncovered_ids
                )
                if coverable_uncovered_ids
                else problem.incidents
            )
            candidates: list[_Candidate] = []
            for volunteer in remaining.values():
                for incident in candidate_incidents:
                    if (incident.id, volunteer.id) in problem.existing_pairs:
                        continue
                    candidate = self._candidate(
                        incident,
                        volunteer,
                        planned_counts[incident.id],
                    )
                    if candidate:
                        candidates.append(candidate)
            if not candidates:
                break
            chosen = max(
                candidates,
                key=lambda item: (
                    item.allocation_score,
                    item.fit_score,
                    item.incident.priority_score,
                    -item.incident.id,
                    -item.volunteer.id,
                ),
            )
            decisions.append(
                AllocationDecision(
                    incident_id=chosen.incident.id,
                    incident_title=chosen.incident.title,
                    incident_location=chosen.incident.location_name,
                    volunteer_id=chosen.volunteer.id,
                    volunteer_name=chosen.volunteer.name,
                    service=chosen.service,
                    fit_score=chosen.fit_score,
                    allocation_score=chosen.allocation_score,
                    breakdown=chosen.breakdown,
                )
            )
            planned_counts[chosen.incident.id] += 1
            del remaining[chosen.volunteer.id]

        for volunteer in remaining.values():
            compatible = any(
                self._matching_services(incident, volunteer)
                for incident in problem.incidents
            )
            reason = (
                "Volunteer is already assigned to every compatible selected incident"
                if compatible
                else "No selected incident requests a registered volunteer service"
            )
            unassigned.append(
                UnassignedVolunteer(
                    volunteer_id=volunteer.id,
                    volunteer_name=volunteer.name,
                    reason=reason,
                )
            )

        return AllocationPlan(
            strategy_key=self.key,
            strategy_name=self.name,
            strategy_version=self.version,
            decisions=tuple(decisions),
            unassigned=tuple(sorted(unassigned, key=lambda item: item.volunteer_id)),
        )
