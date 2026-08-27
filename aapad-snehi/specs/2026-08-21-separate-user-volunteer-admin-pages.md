# Separate User, Volunteer, and Admin pages

Date: 2026-08-21
Branch: `feature/separate-user-volunteer-admin-pages`
Scope: clarify audience-specific frontend routes without adding authentication, RBAC, or changing backend workflows.

## Product outcome

- Provide distinct top-level pages at `/users`, `/volunteers`, and `/admin`.
- Place citizen incident reporting and its reporter privacy/safety guidance on the Users page.
- Keep volunteer registration, preferred work areas, profile, mission matching, and self-claiming on the Volunteers page.
- Keep prioritization, responder comparison, preferred-area context, assignment, and dispatch history on the Admin page.
- Update dashboard calls to action and desktop/mobile navigation to the new audience routes.
- Preserve direct visits to legacy `/report` and `/volunteer` URLs through canonical route aliases.

## Boundaries

- No login, session, authentication, authorization, or RBAC gate is introduced in this prototype.
- Existing incident-report, volunteer, assignment, ingestion, provenance, offline-queue, and safety behavior remains unchanged.
- The Admin page remains a demonstration operations workspace and does not imply production authorization.
- This is a route and information-architecture change; no backend endpoint or database migration is required.

## Verification plan

- Add deterministic tests for canonical routes, trailing slashes, and legacy aliases.
- Verify navigation and all dashboard actions use the canonical audience routes.
- Run frontend tests, TypeScript checking, the production build, and the full backend regression suite.
- Smoke-check canonical and legacy browser routes against the running development server when available.

## Implementation record

- Renamed the citizen reporting screen to `UserPage` and mounted it at `/users` without changing photo, location, verification, consent, or offline-queue behavior.
- Mounted the existing responder workflow at `/volunteers`; `/admin` remains the allocation and dispatch workspace.
- Centralized canonical route constants and legacy aliases, including trailing-slash normalization and browser URL replacement.
- Updated desktop/mobile navigation and every dashboard call to action to use the new canonical audience paths.
- Removed the Admin authentication/RBAC warning banner because those controls are explicitly outside the current prototype scope; the demonstration-console label and human dispatch safeguards remain.
- Documented the public route/access boundary in the README and architecture decision record.
- Verified on 2026-08-21 with 100 backend tests, 7 frontend tests, Python bytecode compilation, TypeScript checking, and the Vite production build.
- Smoke-tested `/`, `/users`, `/volunteers`, `/admin`, `/report`, and `/volunteer` against a local Vite server; every path returned HTTP 200.
