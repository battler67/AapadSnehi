# SACHET India RSS/CAP ingestion service

## Scope

- Branch: `feature/sachet-cap-state-adapter`
- Replace state-specific SACHET sources with the single all-India RSS source:
  `https://sachet.ndma.gov.in/cap_public_website/rss/rss_india.xml`.
- Normalize linked CAP 1.2 documents into the existing `IncidentCandidate` contract.
- Parse optional linked polygon XML and CAP inline point, circle, polygon, area, and
  geocode evidence without introducing crawler or browser automation.
- Poll the national source every five minutes behind the existing live-adapter gate.
- Surface active SACHET incidents in the dashboard's five most relevant external
  signals without changing the existing page layout.
- Preserve the live-ingestion feature gate, source provenance, and independent
  per-source failure handling.

The previously published automated-allocation work remains isolated on
`feature/automated-volunteer-distribution`; this adapter branch starts from `main`.

## Normalization policy

SACHET is an official NDMA/CAP source, so its filter is intentionally broader than
news and web-search filtering:

1. Accept only the exact SACHET HTTPS host and national-RSS, linked-CAP, or
   linked-polygon path shapes.
2. Prefer the English CAP `info` block, while allowing the first available language
   when English is absent.
3. Require an `Actual`, public, non-cancelled, non-expired CAP alert. A meaningful
   official CAP `event` can establish the hazard even when it is not one of the
   portal's 53 news keywords.
4. Prefer CAP points/circles/polygons and external polygon XML. Resolve structured
   area/geocode evidence before sender and headline text, using the India centroid
   only as a documented last resort.
5. Use the RSS item only as a bounded fallback when its linked CAP document is
   temporarily unavailable. Trusted RSS category and state context are enough for
   this fallback; arbitrary feeds do not receive this treatment.
6. Retain SACHET/CAP provenance and `official` verification. Do not promote search,
   news, community, test, exercise, private, cancelled, or expired alerts.

## Fetch and lifecycle policy

- Fetch at most 200 national RSS items and use at most eight concurrent CAP item
  operations. Bound every response with the shared adapter limits.
- Send `If-None-Match` after an ETag is observed and reuse the cached XML on HTTP
  `304`, for fetched RSS, CAP, and polygon documents when the server supplies it.
- Treat the feed as a current snapshot. A successful refresh deactivates incidents
  no longer returned; a provider failure leaves the prior snapshot intact.
- A bad linked item does not fail the national source. Invalid feed XML or an
  unreachable national feed does fail that source and is recorded independently.

## Configuration

`AAPAD_SACHET_POLL_SECONDS` sets the backend polling interval. It defaults to 300
seconds, is active only with `AAPAD_ENABLE_LIVE_ADAPTERS=true`, and accepts `0` to
disable scheduled polling. Existing state-source records are migrated to one enabled
national source without deleting source or incident history.

## Verification

- Endpoint/path validation and unsafe-link rejection.
- Registry discovery and exactly one seeded/API-visible national source.
- Malayalam RSS plus bilingual CAP normalization.
- CAP severity, English selection, structured national geolocation, stable IDs, needs, and
  official provenance.
- Loose RSS fallback, cancellation/expiry filtering, and ETag/304 cache reuse.
- Ingestion-to-dashboard flow for a SACHET incident.
- Full backend tests, frontend tests, typecheck, and production build.

## Implementation record

- Added the registry-backed `SachetCapRssAdapter` and reusable response-metadata
  transport seam without changing other adapter contracts.
- Replaced per-state source seeding with one all-India source, a safe legacy-source
  migration, a national offline/demo source card, and dashboard integration.
- Added bounded CAP concurrency, persistent request sessions, inline/external
  geometry parsing, CAP identifier deduplication, and guarded polygon fallback.
- Added live-gated five-minute backend polling with a process-local ingestion lock.
- Added provider-specific documentation and updated architecture/trust guidance.
- Deterministic verification: 129 backend tests and 7 frontend tests passed.
- Build verification: TypeScript checking and the Vite production build passed.
- Live smoke verification: the public all-India RSS and linked CAP flow normalized
  62 current alerts, with the inspected sample covering Tamil Nadu, Uttar Pradesh,
  Uttarakhand, and West Bengal.
- Secret hygiene: `.env` remains ignored and untracked; the scanned implementation,
  fixtures, environment example, and documentation contain no credential-shaped key.
