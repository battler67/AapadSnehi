# Volunteer distribution strategy experiments

## Branch

`codex/volunteer-distribution-strategies` in the active `aapad-snehi/` checkout.

## Scope

Extend the existing administrator-selected, preview-before-confirmation volunteer
distribution workflow. Preserve the existing balanced greedy strategy and add two
deterministic alternatives without changing assignment persistence or implying
that an algorithm authorizes field deployment.

## Strategy plan

1. **Capacity-aware global optimum** (`global-optimal-v1`): expand each incident
   into a small, transparent number of response slots and use the Hungarian
   assignment algorithm to maximize total fit across the entire selected pool.
2. **Capacity-aware stable matching** (`stable-matching-v1`): volunteers propose
   to compatible incidents in ranked order; incidents retain their strongest
   candidates up to the same response-slot target. Continue until no blocking
   compatible proposal remains.

The response-slot target is a planning heuristic derived from severity, priority,
need count, and existing coverage. It is not a field staffing requirement.

## Invariants

- Only administrator-selected active incidents and selected volunteers participate.
- A volunteer must be exactly `available`, offer a requested registered service,
  and not already hold the same incident pairing.
- Each volunteer receives at most one proposed destination.
- Results are deterministic for identical inputs.
- Preview fingerprints and explicit confirmation remain mandatory.
- Algorithms provide decision support only; coordinators and volunteers retain
  operational authority.

## Verification plan

- Unit tests for optimality, capacity, stability, determinism, duplicate prevention,
  unavailable/incompatible volunteers, and registry metadata.
- API previews for all registered strategies and confirmation provenance.
- Frontend tests/build plus browser verification of selection and comparison text.
- Full backend regression suite.

## Verification log

- `backend/.venv/Scripts/python.exe -m pytest tests/test_allocation.py -q`:
  11 passed. Covers registry metadata, global-plan optimality, stable rejection
  and reproposal, capacity limits, determinism, API previews, atomic commit,
  preview-token protection, and strategy provenance.
- `backend/.venv/Scripts/python.exe -m pytest`: 270 passed. Existing warnings
  are dependency deprecations from Starlette/httpx and joblib/NumPy.
- `web/npm test`: 8 files and 17 tests passed.
- `web/npm run build`: passed. Vite reported the existing warning that the main
  JavaScript chunk exceeds 500 kB.
- Browser check at `http://localhost:5173/admin`: all three strategies appeared
  in the selector; both new explanations rendered; stable matching and global
  optimum each returned a non-mutating preview allocating two selected
  volunteers across two selected incidents; no error overlay appeared.

## Major edits

- Added shared capacity and score helpers plus Hungarian and deferred-acceptance
  implementations under `backend/app/allocation/`.
- Registered both strategies and extended discoverable API metadata with concise
  descriptions and recommended experiment use.
- Added in-context strategy descriptions to the existing Admin distribution panel.
- Expanded `docs/allocation-strategies.md` with formulas, worked examples,
  complexity, trade-offs, safety boundaries, and comparison guidance.
