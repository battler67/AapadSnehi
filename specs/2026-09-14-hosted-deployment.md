# Hosted deployment preparation

User approved a free ephemeral demo deployment (not paid hosting). Use isolated
source-only deployment snapshot branch `codex/render-free-demo`; preserve the
existing worktree and index. No local DB, media, secrets or repository history will
be published in this snapshot. Render account and nested repository access verified.
Free blueprint has no disk; hosted UI warns about resets and fictional data only.

2026-09-15: Explicit source-push authorization received. GitHub connector confirmed
the signed-in owner `battler67`. Source-only root commit `fb161f0` (113 files) pushed
to nested remote branch `codex/render-free-demo`; existing index/branches preserved.
Render free Docker service `srv-dak5522fngtc73bq6tcg` created in Singapore, no disk,
auto-deploy off, health path `/health`. Initial deploy `dep-dak552ifngtc73bq6vrg`
started. Tests: 238 backend passed, 15 frontend passed, production build passed.
Snapshot whitespace check flags a pre-existing blank EOF in edge/__init__.py only.

Completed: https://aapad-snehi.onrender.com . Follow-up commit `df505be` fixes
the hosted homepage overriding the standalone API root. Render deploy
`dep-dak56r6k1f9s73ef5p50` is Live. Browser verified homepage, API-online report
wizard, demo warning, and synthetic text-only submission receipt
`FL-B7951EDAF5E34ACF` / incident 8 with location clarification status. Render logs
confirm database health HTTP 200. No private local records or credentials uploaded.
Hosted route unit test passed. Free storage remains ephemeral; cold starts can
take 50+ seconds. Full rescue assignment/photo flow was not re-tested remotely.

Scope: publish the existing React/FastAPI application with persistent SQLite storage.
Working branch: `feature/citizen-flood-rescue`; preserve all existing changes.

The connected Vercel account returned no accessible teams. Automatic approval review
rejected an unconfigured deploy because the destination and exported contents were
not verified and private data could be included. No deployment was made.

Prepare a portable, single-service Docker build with same-origin frontend/API routing
and a persistent `/app/data` volume. Allowlist source and frontend build inputs;
exclude all local databases, media, secrets, Git metadata and development artifacts.
Validate SPA fallback and API routing locally. Actual hosting awaits a connected
account with persistent storage and approval of the verified source-only payload.

User selected Render. Added Dockerfile, source-only `.dockerignore`, hosted static
entry point, Render blueprint and hosting guide. The browser currently shows Render's
sign-in page; user sign-in is required. Render documents that persistent disks require
a paid service. No recurring charge has been approved or incurred. Docker CLI exists
but its local engine is not running, so a container build has not yet been verified.
The hosted-route test passes (API 404s, SPA fallback, assets and hidden-file protection).
Frontend: 15 tests and same-origin production build passed. Render sign-in reached
GitHub two-factor authentication; the user must complete it in the browser. The
nested active repository remains on its pre-existing branch; no commit/push occurred.
