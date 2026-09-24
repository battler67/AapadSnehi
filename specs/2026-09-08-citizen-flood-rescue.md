# Citizen flood reporting and rescue coordination

Branch: `feature/citizen-flood-rescue`.

## Scope and inspected baseline

Extend the active FastAPI/SQLAlchemy/SQLite and React/Leaflet application. Preserve
the pre-existing uncommitted edge-warning implementation. Existing public prototype
routes have no identity boundary; new operational records must not be exposed or
modifiable through those routes. No production deployment, external notifications,
or image-model calls are part of this work.

## Implementation plan

1. Extend existing Incident and CitizenReport identities with protected operational
   detail tables, places, task state, media and append-only audit events. Add scoped
   credential identities because the application has no existing authentication.
2. Build a working mobile citizen form, durable IndexedDB draft and retry-safe
   submission, private photo upload, list/map, review, assignment and outcome flow.
3. Add explicit grouping, canonical reviewed counts, filters, clarification,
   staleness and deterministic public approximation. Keep legacy routes isolated.
4. Add explicit isolated synthetic seed, migration/operating guide, regression tests
   and integrated browser checks at mobile and desktop sizes.

## Verification record

## Delivered changes

- Added `backend/app/flood/`: protected extensions of existing report/incident IDs,
  hierarchical places, private media, credential identities, rescue teams/tasks,
  explicit state transitions, audit history and version-based write conflicts.
- Isolated protected rows from legacy public ORM queries. Existing public prototype
  routes are not described as authenticated. Original uncommitted edge code remains.
- Added `/flood/report` and `/flood`, linked from Shell and Users. Leaflet clusters,
  synchronized list/geographic summaries, public coordinate approximation, private
  operational details, reporter receipts, human review and rescue progression work
  against the API. Address lookup is gated and remains truthfully unavailable by default.
- Extended the existing IndexedDB database with durable flood drafts, optional
  compressed photographs, metadata suggestions requiring confirmation, explicit retry,
  stable idempotency keys, upload progress and completed-draft cleanup.
- Excluded API/authenticated responses from the existing service worker cache and
  verified production-shell recovery during a fully offline reload.
- Migrated the development SQLite database; nullable coordinates retain unknown
  locations without invented points. A `.before-flood.sqlite` backup precedes rebuild.
- Seeded `backend/data/flood-demo.db` explicitly. Credentials and browser evidence
  are in ignored `.artifacts/`; no production changes or emergency messages were sent.
- Documented setup, configuration, permissions, counting, limitations and walkthrough
  in `aapad-snehi/docs/CITIZEN_FLOOD_RESCUE.md`.

## Verification results (2026-09-09)

- Original baseline: 222 backend tests passed before new risk tests.
- Final full backend suite: **237 passed**, including named-building/unit counting.
- Frontend: 15 tests passed across 7 files, including malformed/valid JPEG GPS metadata.
- TypeScript and Vite production build passed; non-failing 500 kB chunk warning.
- Integrated Playwright passed on the real isolated API/database at 390×844 and
  1440×1000: offline submit, durable refresh/recovery, optional photo upload, public
  privacy, review, assignment, responder progress and resolution with flooding active.
- Production preview additionally passed a fully offline reload with map tile
  requests deliberately failed. API `/health` and `/docs` returned 200.
- `git diff --check` passed; credential-pattern scan of new feature code/docs found
  no secrets. Demo credentials, database and migration backup are ignored by Git.

No live geocoding request was made. New route authentication is local credential
provisioning, not agency SSO; geographic authorization uses normalized city names.
Public photo publication is intentionally disabled. These limits are documented.
