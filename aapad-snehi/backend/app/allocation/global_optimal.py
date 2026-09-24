from __future__ import annotations

from .base import AllocationPlan, AllocationProblem, UnassignedVolunteer
from .capacity import (
    available_volunteers,
    capacity_candidate,
    decision,
    open_capacity,
    unassigned_reason,
)


def _minimum_cost_assignment(costs: list[list[int]]) -> list[int]:
    """Rectangular Hungarian algorithm; returns one column for every row."""

    rows = len(costs)
    if rows == 0:
        return []
    columns = len(costs[0])
    if rows > columns:
        raise ValueError("Hungarian assignment requires at least as many columns as rows")
    u = [0] * (rows + 1)
    v = [0] * (columns + 1)
    matched_row = [0] * (columns + 1)
    previous_column = [0] * (columns + 1)
    infinity = 10**15
    for row in range(1, rows + 1):
        matched_row[0] = row
        minimum = [infinity] * (columns + 1)
        used = [False] * (columns + 1)
        column = 0
        while True:
            used[column] = True
            current_row = matched_row[column]
            delta = infinity
            next_column = 0
            for candidate_column in range(1, columns + 1):
                if used[candidate_column]:
                    continue
                reduced = (
                    costs[current_row - 1][candidate_column - 1]
                    - u[current_row]
                    - v[candidate_column]
                )
                if reduced < minimum[candidate_column]:
                    minimum[candidate_column] = reduced
                    previous_column[candidate_column] = column
                if minimum[candidate_column] < delta:
                    delta = minimum[candidate_column]
                    next_column = candidate_column
            for candidate_column in range(columns + 1):
                if used[candidate_column]:
                    u[matched_row[candidate_column]] += delta
                    v[candidate_column] -= delta
                else:
                    minimum[candidate_column] -= delta
            column = next_column
            if matched_row[column] == 0:
                break
        while True:
            previous = previous_column[column]
            matched_row[column] = matched_row[previous]
            column = previous
            if column == 0:
                break
    assignment = [-1] * rows
    for column in range(1, columns + 1):
        if matched_row[column]:
            assignment[matched_row[column] - 1] = column - 1
    return assignment


class GlobalOptimalStrategy:
    key = "global-optimal-v1"
    name = "Capacity-aware global optimum"
    version = "1.0.0"
    summary = "Maximizes the total fit of the complete selected pool using Hungarian assignment."
    best_for = "Best when overall capability and proximity fit matter more than individual preference stability."

    def allocate(self, problem: AllocationProblem) -> AllocationPlan:
        volunteers, unassigned = available_volunteers(problem)
        incidents = sorted(
            problem.incidents,
            key=lambda item: (-item.priority_score, -item.severity, item.id),
        )
        slots = [
            (incident, slot_index)
            for incident in incidents
            for slot_index in range(open_capacity(incident))
        ]
        candidate_rows = []
        maximum_utility = 0
        for volunteer in volunteers:
            row = []
            for incident, slot_index in slots:
                candidate = None
                if (incident.id, volunteer.id) not in problem.existing_pairs:
                    candidate = capacity_candidate(
                        incident,
                        volunteer,
                        slot_index=slot_index,
                    )
                row.append(candidate)
                if candidate:
                    maximum_utility = max(
                        maximum_utility,
                        int(round(candidate.allocation_score * 1000)),
                    )
            candidate_rows.append(row)

        # One private dummy column per volunteer allows a safe unassigned result.
        infeasible_cost = maximum_utility + 10**9
        costs: list[list[int]] = []
        for row_index, row in enumerate(candidate_rows):
            real_costs = [
                maximum_utility - int(round(item.allocation_score * 1000))
                if item is not None
                else infeasible_cost
                for item in row
            ]
            dummy_costs = [
                maximum_utility if dummy_index == row_index else infeasible_cost
                for dummy_index in range(len(volunteers))
            ]
            costs.append(real_costs + dummy_costs)

        assignments = _minimum_cost_assignment(costs) if volunteers else []
        decisions = []
        for row_index, column_index in enumerate(assignments):
            volunteer = volunteers[row_index]
            candidate = (
                candidate_rows[row_index][column_index]
                if 0 <= column_index < len(slots)
                else None
            )
            if candidate is None:
                unassigned.append(
                    UnassignedVolunteer(
                        volunteer_id=volunteer.id,
                        volunteer_name=volunteer.name,
                        reason=unassigned_reason(problem, volunteer),
                    )
                )
            else:
                decisions.append(decision(candidate))

        return AllocationPlan(
            strategy_key=self.key,
            strategy_name=self.name,
            strategy_version=self.version,
            decisions=tuple(
                sorted(decisions, key=lambda item: (item.incident_id, item.volunteer_id))
            ),
            unassigned=tuple(sorted(unassigned, key=lambda item: item.volunteer_id)),
        )
