# Automated volunteer distribution

Date: 2026-08-21
Branch: `feature/automated-volunteer-distribution`
Scope: let an administrator select multiple incidents and a bounded volunteer pool, generate a deterministic distribution plan, review it, and confirm the assignments as one batch.

## Product outcome

- Add a multi-select allocation workspace to the existing Admin page.
- Require the administrator to explicitly select the disaster places and volunteers included in the run.
- Generate a preview which assigns each eligible selected volunteer to at most one selected incident.
- Spread responders across uncovered incidents before adding extra responders where their capability, distance, availability, and incident urgency produce the strongest marginal score.
- Explain every recommendation, identify selected volunteers who cannot be allocated safely, and require a separate confirmation action before records are created.
- Commit the confirmed plan atomically and refresh volunteer availability, response coverage, priority, and dispatch history.

## Replaceable strategy boundary

- Define allocation inputs and outputs as framework-neutral dataclasses.
- Define a small `AllocationStrategy` protocol with a stable strategy key, name, version, and `allocate()` method.
- Resolve algorithms through a registry instead of importing the default implementation in the API route.
- Ship `balanced-greedy-v1` as the default while allowing a later optimizer to register under a new key without changing persistence, endpoints, or the Admin component.
- Expose registered strategy metadata through the API.

## Default algorithm

The algorithm creates only feasible volunteer/incident pairs: the volunteer must be currently available and must provide at least one service explicitly requested by the incident. It uses the existing explainable volunteer-fit score, then applies:

- an uncovered-incident bonus so selected locations receive initial coverage before avoidable concentration;
- a small incident-priority contribution;
- a load penalty scaled by incident demand, existing response coverage, and assignments already proposed in the current plan.

At each iteration it selects the globally highest adjusted pair, removes that volunteer, updates the incident load, and recomputes remaining marginal scores. Stable ID tie-breakers make the output deterministic. Free-form preferred places remain visible context and are not treated as geocoded proof of deployability.

## Safety and operational boundaries

- Preview is read-only; no volunteer is dispatched merely by running the algorithm.
- Confirmation is an explicit administrator action and creates `assigned` records which still await volunteer acceptance and field instructions.
- Unavailable volunteers and volunteers without a requested service are not assigned, even if selected.
- The strategy can recommend only within the administrator-selected incident and volunteer sets.
- The MVP does not solve routing, shift duration, team composition, equipment, jurisdiction, road safety, or real-time capacity; coordinators must review those constraints.
- No login or RBAC is added under the current prototype scope.

## Verification plan

- Unit-test balanced coverage, compatibility filtering, availability filtering, determinism, and registry lookup.
- API-test read-only preview, atomic confirmation, assignment provenance, availability updates, invalid IDs, and unknown strategies.
- Test frontend distribution helpers/types and run TypeScript plus the production build.
- Run the complete backend and frontend regression suites before publishing the feature branch.

## Implementation record

- Added framework-neutral allocation problem/plan dataclasses, the `AllocationStrategy` protocol, and a registry with discoverable metadata.
- Implemented and registered `balanced-greedy-v1` with feasibility gates, initial coverage, demand-scaled load balancing, stable tie-breaking, explainable breakdowns, and explicit unassigned reasons.
- Added read-only preview and transactional confirmation through `POST /api/allocations/distribute`, plus `GET /api/allocation-strategies` for strategy discovery.
- Added a deterministic preview fingerprint covering selected inputs, state, existing pairs, decisions, scores, and exclusions; changed plans are rejected with HTTP 409 before any write.
- Added the Admin multi-select workspace for disaster places and available volunteers, dynamic strategy selection, grouped plan review, unassigned explanations, and explicit batch confirmation.
- Preserved the manual single-assignment workflow as an operational fallback.
- Added `docs/allocation-strategies.md` with the exact formula, pseudocode-level flow, invariants, API contract, replacement instructions, and limitations.
- Verified on 2026-08-21 with 107 backend tests, 9 frontend tests, Python bytecode compilation, TypeScript checking, the Vite production build, live strategy discovery, and an HTTP 200 Admin route smoke check.
