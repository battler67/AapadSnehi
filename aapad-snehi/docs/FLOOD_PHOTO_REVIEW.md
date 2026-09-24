# Unified reporting and optional image screening

Use Flood Rescue → submit report. `/users`, `/user`, and `/report` redirect to
`/flood/report`; homepage reporting actions use the same flow. The legacy Users
component/API remain for compatibility and historical reports, not top-bar entry.

Reports are received first. Only optional uploaded photographs trigger the existing
OpenAI Responses image client and shared rate/concurrency limits. A resized,
metadata-stripped derivative is sent; address/contact fields and original EXIF are
not sent. Upload UI discloses this. No photograph means no model call.

Each private photo has an advisory result in the additive `flood_photo_reviews`
table. Application startup creates the table for existing databases. No backfill
or retroactive screening is performed. Receipt lookup and authorized incident views
show results; public incident payloads do not. AI never changes incident verification,
counts, urgency, task progress, or report acceptance. Human review is mandatory.

Configure the existing backend-only `OPENAI_API_KEY` and existing model/limits.
Missing config, rate limits, timeout (25 seconds), or provider errors leave the photo
attached with an unavailable state. Duplicate upload retries reuse stored results
without extra AI calls. Process interruption during review may leave pending status;
there is no durable background worker or automatic re-screening of pending photos.
Text submission is unaffected. No secrets should be placed in frontend env files.

Run `python -m pytest` from backend; `npm test` and `npm run build` from web.
Tests stub the provider: no real photos are sent and no API charges incurred.
