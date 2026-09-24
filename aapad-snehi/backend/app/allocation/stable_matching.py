from __future__ import annotations

from collections import deque

from .base import AllocationPlan, AllocationProblem, UnassignedVolunteer
from .capacity import (
    CapacityCandidate,
    available_volunteers,
    capacity_candidate,
    decision,
    open_capacity,
    unassigned_reason,
)


class StableMatchingStrategy:
    key = "stable-matching-v1"
    name = "Capacity-aware stable matching"
    version = "1.0.0"
    summary = "Uses deferred acceptance so volunteers and incidents receive mutually ranked compatible matches."
    best_for = "Best when predictable, defensible matching stability matters more than the maximum total score."

    def allocate(self, problem: AllocationProblem) -> AllocationPlan:
        volunteers, unassigned = available_volunteers(problem)
        incident_by_id = {incident.id: incident for incident in problem.incidents}
        capacity = {
            incident.id: open_capacity(incident)
            for incident in problem.incidents
        }
        preference_candidates: dict[int, dict[int, CapacityCandidate]] = {}
        preferences: dict[int, list[int]] = {}
        volunteer_by_id = {volunteer.id: volunteer for volunteer in volunteers}

        for volunteer in volunteers:
            candidates = {}
            for incident in problem.incidents:
                if capacity[incident.id] <= 0:
                    continue
                if (incident.id, volunteer.id) in problem.existing_pairs:
                    continue
                candidate = capacity_candidate(incident, volunteer, slot_index=0)
                if candidate:
                    candidates[incident.id] = candidate
            preference_candidates[volunteer.id] = candidates
            preferences[volunteer.id] = [
                incident_id
                for incident_id, _candidate in sorted(
                    candidates.items(),
                    key=lambda item: (
                        -item[1].allocation_score,
                        -item[1].fit_score,
                        -incident_by_id[item[0]].priority_score,
                        item[0],
                    ),
                )
            ]

        held: dict[int, list[int]] = {incident.id: [] for incident in problem.incidents}
        next_choice = {volunteer.id: 0 for volunteer in volunteers}
        free = deque(volunteer.id for volunteer in volunteers)
        while free:
            volunteer_id = free.popleft()
            choices = preferences[volunteer_id]
            choice_index = next_choice[volunteer_id]
            if choice_index >= len(choices):
                continue
            incident_id = choices[choice_index]
            next_choice[volunteer_id] += 1
            held[incident_id].append(volunteer_id)
            held[incident_id].sort(
                key=lambda candidate_id: (
                    -preference_candidates[candidate_id][incident_id].fit_score,
                    candidate_id,
                )
            )
            if len(held[incident_id]) > capacity[incident_id]:
                rejected = held[incident_id].pop()
                free.append(rejected)

        matched_ids = {volunteer_id for ids in held.values() for volunteer_id in ids}
        decisions = []
        for incident in sorted(problem.incidents, key=lambda item: item.id):
            for slot_index, volunteer_id in enumerate(held[incident.id]):
                candidate = capacity_candidate(
                    incident,
                    volunteer_by_id[volunteer_id],
                    slot_index=slot_index,
                )
                if candidate:
                    decisions.append(decision(candidate))
        for volunteer in volunteers:
            if volunteer.id not in matched_ids:
                unassigned.append(
                    UnassignedVolunteer(
                        volunteer_id=volunteer.id,
                        volunteer_name=volunteer.name,
                        reason=unassigned_reason(problem, volunteer),
                    )
                )

        return AllocationPlan(
            strategy_key=self.key,
            strategy_name=self.name,
            strategy_version=self.version,
            decisions=tuple(decisions),
            unassigned=tuple(sorted(unassigned, key=lambda item: item.volunteer_id)),
        )
