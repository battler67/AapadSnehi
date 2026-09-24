# Volunteer allocation strategies

## Purpose and workflow

Automatic distribution is decision support for an administrator-selected incident set and volunteer pool. It does not discover volunteers globally, send notifications, or authorize field deployment.

1. The administrator selects 2–10 active disaster places and up to 50 currently available volunteers.
2. `POST /api/allocations/distribute` with `commit: false` builds a read-only preview.
3. The Admin page shows every proposed responder, destination, service, fit score, allocation score, and unassigned reason.
4. The preview includes a deterministic `previewToken` fingerprint.
5. A separate confirmation sends the same selection with `commit: true` and that token.
6. The backend recomputes the plan. If anything relevant changed, the token differs and confirmation returns HTTP 409 instead of dispatching a different plan.
7. A valid confirmation writes all assignments in one transaction, updates volunteer availability and incident coverage, and refreshes priority scores.

Assignments remain in `assigned` status and await volunteer acceptance and coordinator instructions.

## Stable extension contract

Algorithm-independent types live in `backend/app/allocation/base.py`:

- `IncidentAllocationInput` contains incident identity, coordinates, needs, severity, priority, and existing coverage.
- `VolunteerAllocationInput` contains identity, coordinates, registered services/skills, and current availability.
- `AllocationProblem` contains the selected inputs and existing incident/volunteer pairs that cannot be repeated.
- `AllocationDecision`, `UnassignedVolunteer`, and `AllocationPlan` are persistence-neutral outputs.
- `AllocationStrategy` requires `key`, `name`, `version`, and a deterministic `allocate(problem)` method.

The FastAPI route resolves the requested key through `backend/app/allocation/registry.py`. It does not import or branch on a specific algorithm. Persistence, preview fingerprinting, transaction handling, serialization, and the Admin UI therefore remain unchanged when a strategy is replaced.

Registered strategies are discoverable through:

```http
GET /api/allocation-strategies
```

The Admin strategy selector reads this endpoint, so newly registered algorithms appear without changing the component.

## Strategy comparison

| Strategy | Main objective | Strength | Trade-off |
| --- | --- | --- | --- |
| `balanced-greedy-v1` | Choose the best current pair, then recalculate | Fast and easy to follow step by step | An early choice can prevent a better complete plan |
| `global-optimal-v1` | Maximize the sum of scores over the complete allocation | Best overall score for the selected pool | A match can be less intuitive in isolation because it protects a better overall combination |
| `stable-matching-v1` | Produce mutually ranked matches with no blocking pair | Predictable and defensible when both sides have preferences | Does not guarantee the maximum total score |

All strategies are deterministic decision-support tools. They use only the incidents and volunteers selected by the administrator, produce a preview first, and require explicit human confirmation before assignments are written.

## Default algorithm: `balanced-greedy-v1`

### Feasibility gates

A volunteer/incident pair is considered only when:

- both records were explicitly selected by the administrator;
- the incident is active;
- the volunteer's availability is exactly `available`;
- at least one incident need appears in the volunteer's registered services; and
- the volunteer has not already been assigned to that incident.

Skills may improve the existing fit score, but the assigned service must come from registered services. Each volunteer is removed from the candidate pool after one decision, so one distribution run cannot send that person to multiple places.

### Base fit

The allocator reuses `volunteer_fit()` from `backend/app/priority.py`:

```text
base fit = capability (0..45)
         + distance (0..30)
         + availability (0..15)
         + incident urgency (0..10)
```

Distance is Haversine distance between registered coordinates and the incident point. It is approximate straight-line distance, not travel time or a safe-route calculation.

### Marginal allocation score

For each feasible pair in the current iteration:

```text
demand weight = max(
  0.5,
  priority / 100 + severity / 5 + min(1, number of needs / 5)
)

effective load = existing response coverage + responders already proposed here
coverage bonus = 18 when effective load is zero, otherwise 0
priority contribution = priority * 0.10
load penalty = 12 * effective load / demand weight

allocation score = base fit
                 + coverage bonus
                 + priority contribution
                 - load penalty
```

If any selected incident has zero existing/planned coverage and at least one feasible remaining volunteer, the current iteration considers those coverable uncovered incidents first. After initial coverage, all feasible incidents compete using the marginal score. The highest-scoring pair is selected globally, its incident load is updated, and all remaining scores are recomputed. Ties use fit, incident priority, then stable incident/volunteer IDs, making identical inputs deterministic.

This greedy method is transparent and fast for the bounded MVP input, but it is not globally optimal.

## Shared capacity model for the experimental strategies

The global-optimal and stable-matching strategies need a finite number of positions at each incident. They calculate an experimental response-slot target:

```text
target = min(5, max(
  1,
  number of distinct requested services,
  ceil(severity / 2),
  ceil(priority / 25)
))

open slots = max(0, target - existing response coverage)
```

This target is a bounded comparison heuristic, not an operational staffing requirement. It deliberately prevents one incident from absorbing the entire selected volunteer pool. A coordinator must still decide whether the resulting staffing is adequate.

Both strategies use the existing `volunteer_fit()` score and add:

```text
allocation score = base fit
                 + priority * 0.10
                 + 12 for the first uncovered slot
                 - 4 * slot index
```

The slot penalty represents diminishing value from adding several people to the same incident. Compatibility remains a hard gate: a volunteer must be available, must provide a requested registered service, and cannot be assigned to the same incident twice.

## Global optimization: `global-optimal-v1`

This strategy treats distribution as a maximum-weight assignment problem. It asks: "Which complete set of pairings has the highest total allocation score?"

### How it works

1. Expand each incident into its open response slots. For example, an incident with three open slots becomes three assignable columns.
2. Calculate the allocation score for every compatible volunteer/slot pair.
3. Add a private unassigned option for every volunteer. This ensures the optimizer never forces an incompatible match.
4. Convert scores into costs and run the Hungarian assignment algorithm.
5. Return only compatible real-slot matches; return a reason for every unassigned volunteer.

Example score table:

| | Incident A | Incident B |
| --- | ---: | ---: |
| Volunteer 1 | 100 | 99 |
| Volunteer 2 | 98 | 1 |

A greedy first step may choose Volunteer 1 for A and leave Volunteer 2 with B, totaling 101. The global strategy chooses Volunteer 1 for B and Volunteer 2 for A, totaling 197. The first individual match is slightly lower, but the complete plan is much stronger.

The implementation is polynomial-time Hungarian assignment, approximately `O(n^3)` after incident slots and unassigned options are constructed. That is practical within the API's bounded pool of at most 50 selected volunteers. It optimizes the documented score; it does not calculate safe routes, predict field conditions, or prove that the slot target is sufficient.

## Stable matching: `stable-matching-v1`

This strategy uses capacity-aware deferred acceptance. It asks: "Can we produce compatible matches where no unmatched volunteer and incident would both prefer each other over their current result?"

### How it works

1. Each available volunteer ranks compatible incidents using allocation score, fit, incident priority, and stable IDs for tie-breaking.
2. Every unmatched volunteer proposes to their highest-ranked incident not yet tried.
3. Each incident temporarily retains its best-fitting volunteers up to its open capacity and rejects the rest.
4. Rejected volunteers propose to their next choice.
5. The process stops when nobody can make another proposal.

Incidents rank volunteers primarily by capability/proximity fit, while volunteers rank incidents by the full allocation score. "Stable" has a precise, limited meaning here: there is no compatible volunteer/incident pair that would mutually prefer each other under these programmed rankings. It does not mean that an assignment is safe, permanent, accepted by the volunteer, or optimal for total score.

Deferred acceptance requires at most one proposal per compatible volunteer/incident pair, approximately `O(V * I)` proposals plus small capacity-list sorting. It is useful when coordinators want consistent, explainable pairings and fewer obvious preference conflicts.

## Choosing an experiment

- Use **Balanced greedy** for a transparent baseline and rapid coverage.
- Use **Global optimum** to compare the best total score across the whole selected pool.
- Use **Stable matching** when mutually ranked compatibility and predictable reassignment behavior are more important than the maximum score.

Run the same selected incidents and volunteers through multiple preview strategies to compare them. Confirm only one plan. After a commit, availability and coverage change, so later previews correctly use the new operational state.

### Unassigned explanations

Selected volunteers remain unassigned when they are unavailable, provide none of the selected incidents' requested services, or already have assignments for every compatible selected incident. The plan returns the reason rather than forcing an unsafe or duplicate match.

## Replacing or adding an algorithm

Create an implementation with the stable contract:

```python
from app.allocation.base import AllocationPlan, AllocationProblem


class MyOptimizer:
    key = "my-optimizer-v1"
    name = "My constrained optimizer"
    version = "1.0.0"

    def allocate(self, problem: AllocationProblem) -> AllocationPlan:
        # Enforce the documented invariants and return a deterministic plan.
        ...
```

Then register one instance in `backend/app/allocation/__init__.py`:

```python
register_strategy(MyOptimizer())
```

Use a new key when behavior changes materially. Do not silently replace an old key: assignment provenance stores the strategy key, and reproducible review depends on knowing which version produced a plan. Add focused tests for feasibility, determinism, duplicate prevention, incomplete allocation, and any new constraint.

A mixed-integer optimizer, min-cost flow solver, or learned ranker can use the same input/output boundary. A learned model should produce bounded advisory scores; hard safety constraints must remain deterministic outside the model.

## API examples

Preview:

```json
{
  "incident_ids": [1, 2, 3],
  "volunteer_ids": [4, 8, 12, 16],
  "strategy": "balanced-greedy-v1",
  "commit": false,
  "preview_token": "",
  "note": ""
}
```

Confirmation repeats the same input with `commit: true` and the returned `previewToken` as `preview_token`. The token is a consistency fingerprint, not authentication or authorization.

## Known limitations

- Coordinates may be approximate and no road closure, weather, travel-time, shift, equipment, team-composition, jurisdiction, or shelter-capacity constraint is modeled.
- Preferred work areas are free-form display context, not authoritative geofences.
- The strategy does not predict casualties or responder safety.
- SQLite provides MVP transaction behavior; production should use PostgreSQL transactions, row-level concurrency controls, audit events, identity/RBAC, notification acknowledgement, and operational cancellation/reallocation flows.
- Coordinators must review the plan and volunteers must receive instructions and accept safely before travel.
