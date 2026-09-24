# Bluesky sentiment analysis

## Branch

`codex/bluesky-sentiment-analysis`

## Scope

Add optional, backend-only transformer sentiment classification to public Bluesky assistance leads. Preserve deterministic assistance-intent filtering and treat sentiment as advisory metadata rather than evidence of willingness, credibility, or operational suitability.

## Plan

- Use the hosted `cardiffnlp/twitter-roberta-base-sentiment-latest` model through Hugging Face Inference Providers.
- Keep the token backend-only and return a truthful unavailable state when configuration or inference fails.
- Normalize social handles and links before inference as recommended by the model card.
- Attach positive, neutral, or negative labels, scores, model provenance, and a summary to scan results.
- Do not let sentiment change helper matching, verification, assignment, or dispatch.
- Add UI labels, documentation, unit/API tests, and a live Nepal-flood comparison.

## Major edits

- Added a hosted Hugging Face sentiment service with social-text normalization, three-label parsing, secret-safe failures, and a circuit breaker.
- Added optional sentiment configuration and a default per-scan cap of ten matched posts.
- Added sentiment label, score, model provenance, provider status, and aggregate counts to the Bluesky response.
- Added advisory sentiment labels and summaries to the helper UI with an explicit data-sharing notice.
- Kept deterministic intent filtering authoritative for matching; sentiment cannot create, verify, assign, or dispatch a helper.
- Added model, adapter, API, failure, inference-cap, and frontend contract coverage.

## Verification

- Model metadata: Hugging Face reported the selected model live on `hf-inference` for text classification.
- Known-sentence provider smoke test: available; returned neutral at 0.642.
- Targeted backend tests: 18 passed.
- Full backend suite: 251 passed.
- Frontend tests: 15 passed.
- Frontend production build: passed; existing bundle-size warning remains.
- Live raw Nepal evaluation: 25 posts -> 4 positive, 13 neutral, 8 negative, 0 unavailable.
- Integrated assistance scan: 25 scanned, four deduplicated leads -> 1 positive, 3 neutral, 0 negative/unavailable.
- Qualitative finding: positive sentiment did not increase reliable helper count; some positive posts were non-assistance, while active-aid posts were neutral.
- UI timeout diagnosis: the shared client aborted after 8 seconds while sequential hosted sentiment calls could each wait 12 seconds.
- Timeout fix: the Bluesky scan now has a 60-second client allowance and runs at most four bounded sentiment calls concurrently.
