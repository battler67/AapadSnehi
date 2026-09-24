# Volunteer distribution strategy experiments

## Branch and scope

Implemented on `codex/volunteer-distribution-strategies`. The existing
preview-before-confirmation workflow remains the operational boundary. This
change keeps `balanced-greedy-v1` and adds two deterministic comparison
strategies without making algorithmic output an authorization to dispatch.

## Added strategies

1. `global-optimal-v1` expands incidents into bounded response slots and uses
   Hungarian assignment to maximize the total score across the selected pool.
2. `stable-matching-v1` uses capacity-aware deferred acceptance: volunteers
   propose in ranked order and incidents retain their strongest compatible
   candidates until proposals are exhausted.

The shared response-slot target uses severity, priority, distinct needs and
existing coverage. It is an experimental comparison heuristic, not a staffing
requirement.

## Safety invariants

- Only explicitly selected active incidents and volunteers participate.
- Volunteers must be available, offer a requested registered service and not
  already hold the same incident pairing.
- Each volunteer receives at most one proposed destination per run.
- Identical inputs produce deterministic output.
- A fingerprinted preview and separate human confirmation remain mandatory.

## Verification

- Allocation tests: 11 passed, including global optimality, stable rejection
  and reproposal, capacity, determinism and all three API strategy paths.
- Complete backend suite: 270 passed.
- Frontend suite: 17 passed across 8 files.
- Production frontend build: passed with the existing large-chunk warning.
- Browser verification: both new strategies appeared on `/admin`, changed the
  explanation, and generated a two-volunteer/two-incident preview. The preview
  was not confirmed, so the browser check did not create assignments.

See `docs/allocation-strategies.md` for formulas, examples, complexity,
trade-offs and selection guidance.
