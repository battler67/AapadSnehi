# Bluesky inclusive helper filter

## Branch

`codex/bluesky-inclusive-helper-filter`

## Scope

Broaden the read-only Bluesky helper scan so that human reviewers can see lower-confidence assistance leads without presenting them as verified volunteers or automatically dispatching them.

## Plan

- Classify explicit offers, active aid, institutional support, and fundraising/donation leads separately.
- Keep negated or request-only posts excluded.
- Allow a recognized hazard in the user query to supply low-confidence disaster context when a returned thread post omits the hazard term.
- Return the confidence, intent category, and disaster-context source to the UI.
- Deduplicate by author while retaining the strongest matching post.
- Keep all Bluesky matches unverified and require human review and consent.
- Add regression tests based on the observed Nepal flood posts.

## Major edits

- Added tiered assistance-intent classification with explicit, active-aid, institutional, and fundraising categories.
- Added query-derived disaster context for assistance posts that omit the hazard term.
- Added strongest-per-author deduplication and confidence/context fields to the API.
- Added visible confidence, category, and query-context warnings to the helper page.
- Kept low-confidence and query-context leads out of automatic incident ingestion.
- Added regression coverage based on the observed Nepal flood results.

## Verification

- `python -m pytest`: 245 passed.
- Targeted Bluesky/social tests: 12 passed.
- `npm test`: 15 passed.
- `npm run build`: passed; existing bundle-size warning remains.
- `git diff --check`: passed; repository line-ending warnings only.
- Live `Nepal flood` verification: 25 posts scanned, four assistance leads returned (two medium-confidence and two low-confidence), versus zero under the previous filter.
