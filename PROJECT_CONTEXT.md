# Project context

Last curated: 2026-08-27

## Product state

AapadSnehi is a standalone disaster-response coordination prototype. The active
implementation lives in aapad-snehi/ and combines:

- a FastAPI backend with SQLite for local development;
- a React/Vite progressive web frontend;
- incident normalization, deduplication, explainable priority scoring, and source
  provenance;
- citizen photo reports with advisory AI screening and human review;
- volunteer profiles, mission matching, and explicit administrator dispatch;
- deterministic demo data plus optional, gated external adapters.

The Users, Volunteers, and Admin pages are public prototype routes. They are
separate workflows, not security boundaries. Do not describe the current build as
production-ready or access-controlled.

## Decisions that must remain explicit

1. Demo mode is the safe default. Live adapter requests require
   AAPAD_ENABLE_LIVE_ADAPTERS=true and any provider-specific configuration.
2. Seeded/fallback records are demo data. Social and news results are unverified
   leads. Official provenance applies only to records derived from an official
   source and does not by itself justify dispatch.
3. Bluesky helper search is backend-only, read-only, and deterministic. It uses
   disaster keywords plus explicit offer-to-help phrases; it does not register
   volunteers, contact users, or use sentiment/Transformer models.
4. Citizen image screening is advisory. It cannot establish authenticity,
   location, recency, causation, or severity. Human review and retained provenance
   remain required.
5. Volunteer allocation is decision support. Availability, capability, distance,
   local conditions, and an administrator's explicit confirmation govern dispatch.
6. Credentials stay server-side in ignored local configuration. .env.example
   must contain placeholders only.

## Integration status

- Seed, USGS, NASA EONET, ReliefWeb, GDELT, government feed, Serper, Google News,
  SACHET CAP, and Bluesky adapter code is present.
- Live external calls are optional and provider failures are isolated.
- OpenAI/Cloudinary is the active hosted image-review path when configured.
- Qwen/Hugging Face and the blip-caption-api/ Space are retained as inactive
  experiments, not required runtime dependencies.
- bluesky_test.ipynb is historical and sanitized; the application implementation
  is under aapad-snehi/backend/app/adapters/bluesky.py.

## Continuation guide

- Read aapad-snehi/README.md, aapad-snehi/docs/, and the relevant spec before
  changing a subsystem.
- Put new approved plans and implementation records in the top-level specs/
  directory.
- Preserve source trust labels, ownership/safety checks, explicit confirmation
  steps, and unrelated working-tree edits.
- Restart the exact backend process before runtime/API verification; source changes
  do not update an already-running process.
- Run backend tests, frontend tests, the TypeScript/Vite build, and a staged secret
  scan before publishing changes.

This file is curated repository context. Private Codex session memory and
cross-project history are intentionally not copied into the repository.
