# Disaster news and web-search adapters

Date: 2026-08-21
Branch: `feature/disaster-news-adapters`
Scope: extend `aapad-snehi/` without changing the existing dashboard layout or weakening live-provider gates.

## Product outcome

- Add a Serper-backed India disaster web-search adapter that accepts at most the five highest-ranked results which pass the portal's disaster and location filters.
- Add a reusable Google News RSS adapter and configure the requested India headlines, AI, and India technology feeds.
- Send accepted records through the existing validation, provenance, deduplication, priority scoring, incident storage, dashboard, map, and assignment flow.
- Keep news and search results `unverified`; they are operational review signals, not official public warnings.

## Security and operational boundaries

- The Serper credential is read only from `AAPAD_SERPER_API_KEY`; no real credential is stored in source, fixtures, documentation, or Git.
- Live providers remain disabled unless `AAPAD_ENABLE_LIVE_ADAPTERS=true` is set before API startup.
- Serper requests are restricted to the reviewed HTTPS search endpoint. Google News RSS requests are restricted to the HTTPS `news.google.com` host.
- Provider responses retain the existing 12-second timeout, redirect refusal, and 4 MiB response limit.
- Each provider records an independent ingestion result so one external failure does not stop the remaining sources.

## Implementation plan

1. Add a decorator-based adapter registry and a reusable bounded JSON POST seam.
2. Implement Serper search and Google News RSS adapters with shared article normalization.
3. Add the requested sources idempotently for both new and existing development databases.
4. Make the existing pipeline action use live mode only when the backend explicitly reports live mode.
5. Show five ranked incidents in the existing dashboard priority list without adding implementation-summary panels.
6. Add adapter, filtering, registry, security, and integration tests; run backend/frontend builds and a credential scan.

## Verification record

Implemented on `feature/disaster-news-adapters`:

- Added a decorator-based adapter registry and bounded GET/POST/text request helpers.
- Added strict-host Serper and Google News RSS adapters, India-focused disaster/location filtering, relative-date parsing, and at-most-five result limits.
- Added all requested RSS sources and idempotent source seeding for existing databases.
- Added snapshot retirement for successfully refreshed search/news result sets; provider failures retain the last successful records.
- Added a dashboard projection for up to five active external signals and reused the existing incident-card visual system with visible provenance and unverified status.
- Updated the existing pipeline action to request live providers only when the backend reports `live-enabled` mode.
- Added README, architecture, environment-template, and adapter-extension documentation. No real credential was persisted.

Verification completed:

- `python -m pytest -q`: 35 passed.
- `python -m pytest tests\test_news_adapters.py -q`: 14 passed, including registry, endpoint restrictions, top-five filtering, snapshot retirement, and dashboard integration.
- `python -m compileall -q app tests`: passed.
- `npm test`: 4 passed across 2 files.
- `npm run build`: TypeScript and Vite production build passed; 1,731 modules transformed.
- Credential-free live smoke against the supplied Google News India RSS URL parsed successfully and accepted zero current records, which is a valid conservative filter result.
- Serper live execution was not performed with the chat-exposed credential. The request contract and full ingestion/dashboard path were verified with deterministic fixtures; live use requires a rotated key in `AAPAD_SERPER_API_KEY`.
- Credential scan found no 40-character hexadecimal candidates or assigned credential-shaped values outside dependency locks.
