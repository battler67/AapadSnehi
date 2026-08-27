# Volunteer preferred work areas

Date: 2026-08-21
Branch: `feature/volunteer-preferred-places`
Scope: extend volunteer registration and admin allocation context without changing explicit dispatch controls.

## Product outcome

- Ask every newly registered volunteer for one to five preferred work areas such as cities, districts, or states.
- Persist normalized, human-readable preferences and return them through volunteer APIs.
- Show preferences on the volunteer profile and beside every recommended responder in the admin allocation view.
- Backfill existing volunteer records with their home location as a safe legacy default.

## Boundaries

- Preferred areas are dispatch context, not proof of availability, training, jurisdiction, or safety.
- Existing capability, availability, distance, urgency, verification, and explicit administrator dispatch controls remain unchanged.
- Each place is trimmed, deduplicated case-insensitively, and limited to 120 characters; the list is limited to five entries.
- The SQLite development database receives an idempotent additive column migration. No existing volunteer or assignment data is removed.

## Verification plan

- Test API validation, normalization, serialization, registration, and assignment compatibility.
- Test migration/backfill against an existing SQLite volunteers table.
- Verify demo fallback data, volunteer profile rendering, admin responder rendering, TypeScript, and production build.

## Implementation record

- Added the additive `preferred_places_json` volunteer field, API validation/normalization, camel-case serialization, seeded examples, and legacy-record backfill.
- Added an idempotent SQLite compatibility migration which runs before seed/backfill processing.
- Added a required semicolon-separated registration control, volunteer-profile display, and admin responder display without introducing new dashboard cards or sections.
- Kept responder scoring and explicit assignment behavior unchanged; preferred areas are visible decision context only.
- Verified on 2026-08-21 with 100 backend tests, 5 frontend tests, Python bytecode compilation, TypeScript checking, and the Vite production build.
- Confirmed the running local API migrated existing volunteers and returns a non-empty `preferredPlaces` list for every record.
