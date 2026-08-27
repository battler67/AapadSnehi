# Hosted Qwen citizen-report image screening

## Scope

- Branch: `feature/qwen-image-triage`, stacked on the completed hosted BLIP report
  triage branch.
- Replace the unavailable BLIP Space runtime with the Hugging Face routed
  `Qwen/Qwen3-VL-2B-Instruct:featherless-ai` vision service.
- Keep inference remote. Do not install or cache model weights, Torch, or
  Transformers in the AapadSnehi development environment.
- Preserve the existing private-image, three-way moderation, provenance, and
  manual-review behavior while making the vision provider replaceable.
- Record provider, model, prompt version, structured visible evidence, hazards,
  observations, decision, and reason for an auditable report trail.

## Dual-check decision policy

The vision model supplies a factual caption and a constrained visible-evidence
assessment. An independent deterministic policy applies the project's disaster
keyword taxonomy to the caption and observations.

1. `accepted`: the model reports visible disaster evidence, supplies a canonical
   hazard, and the deterministic classifier independently finds the same hazard.
2. `rejected`: the model reports no disaster evidence, the deterministic classifier
   finds no hazard, and an explicit ordinary-scene pattern matches.
3. `needs_volunteer_review`: the model is uncertain, either check contradicts the
   other, the evidence is weak, the response is malformed, the service is
   unavailable, or a local provider-call limit is reached.

This policy only screens visible image content. It does not prove location,
timestamp, authenticity, causation, scope, or severity. Accepted incidents keep the
`ai_screened` provenance label and can still be reviewed by an operator.

## Provider and image contract

- The backend calls the fixed Hugging Face router chat-completions endpoint with a
  backend-only token and a versioned prompt.
- The model must return bounded JSON containing `caption`, `disaster_evidence`,
  `hazards`, and `observations`; unexpected values fail closed to manual review.
- Before inference, the backend decodes the image, applies EXIF orientation,
  rejects unsafe or invalid images, removes metadata, resizes the longest edge to
  1280 pixels, and emits a bounded JPEG inference copy. The original private upload
  remains unchanged.
- A process-local rolling hourly call limit and concurrency bound protect the demo
  budget. They are operational safeguards, not a distributed billing guarantee.
- Provider failures are not retried automatically and can never automatically
  reject a citizen report.

## Compatibility and migration

- New settings use `AAPAD_HF_TOKEN`, `AAPAD_CAPTION_MODEL`,
  `AAPAD_CAPTION_TIMEOUT_SECONDS`, and `AAPAD_CAPTION_MAX_CALLS_PER_HOUR`.
- `AAPAD_BLIP_HF_TOKEN` remains a one-release token fallback. The legacy BLIP URL is
  not reused.
- SQLite startup migration adds nullable/default-safe provider, prompt-version, and
  structured-analysis fields without changing existing report decisions.
- The current report and incident APIs remain backward compatible; new audit
  fields are additive.

## Verification plan

- Unit-test preprocessing, provider payloads and response validation, rate limiting,
  timeout/error handling, and the complete dual-check decision matrix.
- Verify API persistence, migration, moderation, and dashboard/admin/volunteer
  visibility with provider calls mocked.
- Run the complete backend and frontend suites, production build, compilation,
  secret scan, and Git diff/status checks.
- Make exactly one authorized live provider request with a public Hugging Face
  documentation image. Never send a citizen upload or download model weights.
- Document the evaluated alternatives, model-selection rationale, provider limits,
  and the retained legacy BLIP prototype.

## Implementation record

- Replaced the BLIP/Gradio transport with the fixed Hugging Face router chat API
  using `Qwen/Qwen3-VL-2B-Instruct:featherless-ai`; no model runtime or weights are
  installed locally.
- Added EXIF-aware bounded preprocessing, a one-request-per-report transport,
  structured output validation, a process-local hourly call guard, and the
  conservative dual-check decision policy.
- Added migration-safe provider, prompt-version, and structured-analysis audit
  fields while preserving existing automated decisions and manual moderation.
- Updated the user consent copy, admin evidence audit display, configuration,
  architecture record, operations guide, and model comparison. The BLIP Space is
  retained as a documentation-marked legacy prototype.
- One live provider request used only the fixed public Hugging Face car image. It
  returned valid structured no-disaster output, and cache checks before and after
  confirmed that no evaluated model weights were downloaded.
- Application implementation commit: `c15c4b2`. Final checks passed with 171
  backend tests, 7 frontend tests, the TypeScript/Vite production build, Python
  compilation, diff checks, and credential-shaped-value scanning.
