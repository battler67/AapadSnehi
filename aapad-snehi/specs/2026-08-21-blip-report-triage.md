# Hosted BLIP citizen-report triage

## Scope

- Branch: `feature/blip-report-triage`, stacked on the completed national SACHET
  branch until the feature branches are integrated.
- Convert `mural13/blip-caption-api` from a static template to a Gradio Space
  prepared for ZeroGPU using `Salesforce/blip-image-captioning-base`.
- Keep model weights and inference in the Hugging Face Space. Do not install Torch,
  Transformers, or model weights in the AapadSnehi development environment.
- Send validated citizen-report image bytes from the FastAPI backend to the hosted
  caption service; never call the model directly from the browser.
- Classify the returned caption into `accepted`, `needs_volunteer_review`, or
  `rejected` using a deterministic, independently replaceable policy.
- Persist the caption, decision, reason, model identity, and review timestamps so
  operators can audit and override model triage.
- Keep accepted community evidence labelled `ai_screened`, never `official`.

## Decision policy

The caption model describes visible content; it does not prove location, recency,
authenticity, causation, or the reporter's full claim. The policy therefore uses
three outcomes:

1. `accepted`: caption contains clear visible disaster/damage evidence. Activate the
   incident for the admin queue, dashboard, map, and volunteer allocation with an
   `ai_screened` trust label.
2. `rejected`: caption clearly describes ordinary/non-disaster content and contains
   no disaster or visible-damage evidence. Preserve a private audit record but keep
   the incident inactive and return the rejection immediately.
3. `needs_volunteer_review`: model unavailable, malformed/low-information caption,
   or ambiguous visible evidence. Preserve
   the report and inactive incident in the review queue.

Manual review may approve or reject held/rejected reports. Approval activates the
incident as `community_reviewed`; rejection keeps it inactive. This prototype has no
login/RBAC, so the review control is operational-demo functionality rather than an
authorization boundary.

## Hosted API contract

- The named Gradio `/caption` API accepts one uploaded image and returns a bounded
  caption plus model identity.
- A public Space needs no token. A private Space can use an optional least-privilege
  Hugging Face read token configured only in the backend.
- CORS is unnecessary because only the backend calls the Space.
- The Space runtime downloads the public BLIP base weights at startup; local
  repository checks use mocks and static compilation only.

## Failure and privacy policy

- A caption-provider failure must never reject a possibly genuine emergency. It
  routes the report to `needs_volunteer_review`.
- The backend enforces its existing 6 MiB image limit before the provider call and
  uses a bounded timeout. The Space independently limits decoded pixels.
- Submitted evidence remains a private backend artifact; the dashboard receives the
  caption and incident fields, not the image or reporter contact details.
- No submitted images, captions, or credentials are logged by application code.

## Verification plan

- Unit-test the independent caption decision policy across clear disaster,
  non-disaster, and ambiguous captions.
- Mock hosted responses for accepted, rejected, held, unavailable, malformed, and
  timeout paths; assert persistence, activity, trust labels, and API responses.
- Test report review endpoints and dashboard/admin visibility rules.
- Test frontend result messaging and review queue actions.
- Validate Space code without importing/downloading the model locally, deploy it,
  activate eligible compute, then smoke-test the named API with a small image.
- Run the complete backend test suite, frontend tests, TypeScript check/build,
  secret scan, and repository status checks before publishing.

## Implementation record

- Space source deployed at commit `ba2d868`; no model weights, Torch, or
  Transformers were downloaded to the development machine.
- Enabling ZeroGPU returned HTTP 402 because this Hugging Face account must
  subscribe to PRO, wait until it is 30 days old, or receive a community grant.
- The application integration remains fail-safe while the Space is paused: provider
  failure always produces `needs_volunteer_review`, never automatic rejection.
- Verification passed: 144 backend tests, 7 frontend tests, TypeScript/Vite
  production build, Space AST parsing, diff checks, and secret scanning.
- Live caption smoke testing remains pending because the Space runtime is paused;
  local tests use injected captions and never load the model.
