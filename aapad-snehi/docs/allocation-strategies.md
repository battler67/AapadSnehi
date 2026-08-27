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
