# Unified citizen reporting

Branch: codex/flood-photo-review (outer repository). Preserve existing changes.
Consolidate Users navigation into Flood Rescue reporting. Reuse the existing
OpenAI caption client for optional uploaded photographs only. Persist per-photo
advisory results privately; never alter incident verification, urgency or tasks.
Save reports and photos before remote screening; failures require human review.
No real provider calls in tests and no Render redeployment in this task.

Verification: backend and frontend suites, production build, local browser.

Completed locally: additive PhotoReview table, reuse of existing OpenAI client and
limiter, private receipt/operator results, upload dedupe avoids repeat calls,
bounded screening failure preserves attachment. Removed Users nav; legacy routes
and homepage buttons open /flood/report. Old APIs retained for compatibility.
React checklist applied: removed unused legacy page import, typed review payloads,
keyed per-photo results, no new effects or unsafe HTML.

Verification: 240 backend tests passed (including two new integrated API tests),
15 frontend tests passed, production build passed (existing large-chunk warning).
Local backend restarted: additive table created; /health database connected.
Browser verified /users canonical redirect and optional-photo explanation. Provider
success/failure and retry/privacy tested with stubs, not real OpenAI. No paid calls.
Pending screening after a process interruption has no automatic worker recovery;
documented in docs/FLOOD_PHOTO_REVIEW.md. No deployment or push performed.
