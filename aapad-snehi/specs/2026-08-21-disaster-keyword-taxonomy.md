# Disaster keyword taxonomy

Date: 2026-08-21
Branch: `feature/disaster-keyword-taxonomy`
Scope: extend the shared article normalizer used by web-search and RSS adapters without changing the existing UI layout or trust model.

## Product outcome

- Store exactly 53 high-signal disaster keywords in a dedicated, reviewable data file.
- Map each keyword to a canonical hazard type used by incident filters, scoring, maps, and allocation.
- Match phrases at word boundaries and recognize common suffixes such as plurals, `-ed`, and `-ing`.
- Continue requiring usable location evidence before a news/search item becomes an operational incident.
- Add conservative default response needs by hazard so volunteer-fit ranking remains useful when an article does not state needs explicitly.

## Boundaries

- Search and RSS results remain `unverified`; keyword detection never makes an article an official warning.
- The list broadens common natural-hazard coverage but does not justify a literal claim that every possible disaster or language is detectable.
- Specific phrases take precedence over shorter phrases to reduce ambiguous classification.
- The backend fails fast if the keyword file is missing, malformed, duplicated, or no longer contains exactly 53 entries.

## Verification plan

- Assert the taxonomy contains exactly 53 unique keywords.
- Cover floods/flooding, earthquakes, landslides, thunderstorms, heavy rain, cyclones, wildfire, heat, drought, tsunami, volcano, avalanche, cold, and structural failures.
- Verify word boundaries avoid false positives.
- Verify article normalization merges explicit and hazard-default needs.
- Run the complete backend suite, frontend tests/build, compilation, and credential scan.

## Implementation record

Implemented on `feature/disaster-keyword-taxonomy`:

- Added `backend/app/data/disaster_keywords.json` with exactly 53 unique phrases across 14 canonical hazards and conservative allocation needs.
- Replaced the inline normalizer dictionary with a validated file loader that fails fast on missing/malformed data, duplicates, unsupported needs, or count drift.
- Added case-insensitive, word-boundary-aware phrase matching with flexible spaces/hyphens and common final suffixes.
- Evaluates longer phrases first and preserves the existing location-evidence and unverified-source gates.
- Merges explicit article needs with hazard defaults so existing volunteer suggestions rank suitable capabilities without changing dispatch controls.
- Documented taxonomy scope, extension rules, limitations, and the allocation connection in the README, architecture record, and adapter guide.

Verification completed:

- Taxonomy audit: 14 hazards, 53 keywords, 53 unique keywords.
- `python -m pytest -q`: 97 passed.
- `python -m pytest tests\test_normalizer.py -q`: 65 passed, including every configured keyword, common inflections, false-positive boundaries, and volunteer-fit ranking.
- `python -m compileall -q app tests`: passed.
- `npm test`: 4 passed across 2 files.
- `npm run build`: TypeScript and Vite production build passed; 1,731 modules transformed.
- Credential scan found no 40-character hexadecimal candidates or assigned credential-shaped values outside dependency locks.
