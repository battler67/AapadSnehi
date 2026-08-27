# OpenAI verification and Cloudinary evidence storage

## Scope

- Branch: `feature/openai-cloudinary-report-review`, based on merged `main`.
- Make OpenAI Responses API vision the active citizen-image screening provider.
- Keep the Hugging Face provider implementation and its research history in the
  repository, but disconnect it from application startup and report processing.
- Store new citizen evidence in Cloudinary using authenticated delivery; expose a
  backend review URL rather than a public Cloudinary URL.
- Show every review-pending citizen report, caption, and evidence image in both the
  volunteer and admin workspaces. Keep the existing no-login/RBAC prototype boundary.
- Delete the Cloudinary asset before a report can be marked rejected. Retain assets
  for accepted, review-pending, and manually approved reports.

## Credential contract

- `OPENAI_API_KEY` is backend-only.
- `CLOUDINARY_KEY` is one full Cloudinary API environment value in the form
  `cloudinary://api_key:api_secret@cloud_name`. Also accept the standard separate
  `CLOUDINARY_CLOUD_NAME`, `CLOUDINARY_API_KEY`, and `CLOUDINARY_API_SECRET` values
  for deployment flexibility.
- Real credentials belong only in ignored `.env`; `.env.example` contains empty
  placeholders. Process environment values override `.env`.
- Never expose credentials, raw provider error bodies, or reporter contact details
  through the frontend or logs.

## Processing and decision policy

1. Validate and safely preprocess the uploaded JPEG, PNG, or WebP.
2. Generate the report tracking identifier and upload the original bytes to an
   authenticated Cloudinary asset under `aapad-snehi/reports`.
3. Send only the bounded, metadata-free inference JPEG to OpenAI
   `gpt-4.1-mini` using `POST /v1/responses`, `store: false`, low image detail, and a
   strict JSON schema.
4. Request a short factual description, `yes/no/unclear` visible-disaster evidence,
   canonical hazards, and bounded visible observations.
5. Automatically accept only when OpenAI, the deterministic 53-keyword/damage
   policy, and the reporter-selected hazard agree. Otherwise preserve the report as
   `needs_volunteer_review`; OpenAI never automatically rejects a report.
6. Provider or Cloudinary failure preserves a local private fallback and routes the
   report to volunteer review. A possible emergency must not disappear because an
   external service is unavailable.
7. Manual approval retains evidence and activates the incident as
   `community_reviewed`. Manual rejection must delete Cloudinary/local evidence and
   clear its stored locator before the rejection is committed.

## Persistence and API compatibility

- Add migration-safe Cloudinary public ID, asset ID, format, and storage-status
  fields to citizen reports.
- Preserve the existing AI caption/model/provider/prompt/analysis fields and manual
  moderation endpoint.
- Add an image-review endpoint that returns a short-lived signed Cloudinary URL or
  the private local fallback. Rejected reports expose no image.
- Add `imageAvailable` and `imageUrl` to report serialization without exposing raw
  storage identifiers.

## Verification

- Mock OpenAI Responses request/structured-output/error behavior and verify no HF
  request is made by application report processing.
- Mock Cloudinary authenticated upload, signed review URL, destroy, and compensation
  behavior; verify rejection cannot commit when deletion fails.
- Cover accepted, mismatched, no-disaster, unclear, provider failure, storage
  failure, manual approval, manual rejection, admin visibility, and volunteer
  visibility.
- Use the supplied ignored credentials only for minimal live smoke checks. Never
  upload a citizen image during verification, never print keys, and clean up any
  temporary Cloudinary smoke asset.
- Run complete backend/frontend suites, production build, Python compilation, diff
  checks, secret scanning, and clean Git checks before publishing.

## Implementation record

- Active provider: `OpenAIVisionCaptionClient` over `POST /v1/responses`; retained
  Hugging Face classes and smoke script are not imported by application startup.
- Added authenticated Cloudinary upload, expiring review access, rejection deletion,
  local failure fallback, additive SQLite fields, and non-secret report URLs.
- Added the pending review queue and evidence previews to the Volunteer page while
  retaining the Admin queue and existing visual system.
- Verification: backend suite, frontend tests/build, Python compilation, secret scan,
  and credential-safe provider smoke checks. Exact results are recorded in the
  branch handoff/commit after final verification.
