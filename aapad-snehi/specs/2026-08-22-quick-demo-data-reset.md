# Quick-demo data expansion and allocation reset

Date: 2026-08-22
Branch: `feature/bluesky-response-intelligence`

## Scope

- Show three deterministic sample helper cards beneath the Bluesky flood search.
- Use non-resolving `did:example:` IDs and `.invalid` handles so samples cannot be mistaken for real accounts.
- Expand the deterministic volunteer pool from 4 to 12 seeded profiles across the demo incident locations and services.
- Make volunteer seeding idempotent by phone so missing demo profiles are added to an existing database without duplicating records.
- Remove the current local assignment records and restore assignment-limited volunteers to `available` for the live allocation demonstration.

The reset is intentionally a one-time local data operation. Application startup does not delete future assignments created during the demo.

## Verification

- Live API: 13 total volunteers, 13 available volunteers, 0 assignments, and 0 active assignments.
- Backend regression: 202 tests passed.
- Frontend regression: 5 files and 11 tests passed.
- TypeScript check and Vite production build passed.
- Diff whitespace check passed.
