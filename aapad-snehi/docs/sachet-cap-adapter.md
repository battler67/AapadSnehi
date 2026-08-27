# SACHET India RSS/CAP adapter

The `sachet` adapter consumes the National Disaster Management Authority's
all-India RSS feed and normalizes each linked Common Alerting Protocol (CAP) 1.2
alert into the portal's shared incident contract. It is an HTTP/XML ingestion
service, not a crawler: the feed, CAP-detail path, and optional polygon path are
known in advance and strictly allowlisted.

Provider references:

- [SACHET National Disaster Alert Portal](https://sachet.ndma.gov.in/)
- [SACHET CAP/RSS feed page](https://sachet.ndma.gov.in/CapFeed)
- [CAP XML integration and ETag guide](https://sachet.ndma.gov.in/docs/Integration_Guide_For_Agencies.pdf)

## National source and scheduling

The application seeds exactly one enabled SACHET source:

```text
https://sachet.ndma.gov.in/cap_public_website/rss/rss_india.xml
```

Older databases that contain state-specific SACHET sources are migrated safely:
the first legacy source becomes `sachet-india`, remaining state sources are marked
`superseded`, and their old state-feed incidents are deactivated until refreshed by
the national source. No source or incident history is deleted.

Scheduled polling is active only when the existing live-adapter gate is enabled:

```powershell
$env:AAPAD_ENABLE_LIVE_ADAPTERS="true"
$env:AAPAD_SACHET_POLL_SECONDS="300"
```

The default interval is five minutes. A positive interval runs SACHET ingestion
once when the API starts and periodically thereafter. Set the value to `0` to
disable the scheduler and retain manual refresh only. A process-local ingestion
lock prevents a scheduled refresh and an operator-triggered refresh from writing
concurrently. A production multi-worker deployment should move the schedule and
distributed lock to the documented worker/queue architecture.

## Parser flow

1. Validate and fetch the exact national RSS URL.
2. Parse and deduplicate RSS `<item>` elements in feed order, up to 200 items.
3. Validate every item link as the exact same-host `FetchXMLFile` path with one
   bounded `identifier` query value.
4. Fetch linked CAP documents with at most eight concurrent item operations.
5. Prefer an English `info` block, otherwise use the first available language.
6. Parse CAP identity, lifecycle, event, severity, description, instructions,
   area descriptions, geocodes, inline points/circles/polygons, and optional
   `Polygon URL` parameters.
7. Validate and parse a linked `FetchPolygonXMLFile` document when inline geometry
   is absent. Both CAP-style latitude/longitude and KML longitude/latitude
   coordinate order are supported.
8. Emit normalized candidates. A bad linked item can fall back to its recent RSS
   summary without failing other items or the national feed.

All HTTP responses retain the shared 12-second timeout, redirect rejection, and
4 MiB size limit. A persistent HTTP client is used for one feed run so SACHET
cookies and connection pooling carry across RSS, CAP, and polygon requests. If
the provider returns `401`, `403`, or `404` for the first polygon request, further
polygon probes are skipped for that run; area, geocode, sender, and India fallback
evidence remain available.

## Deduplication and lifecycle

The CAP `identifier` is the primary external ID. If CAP is temporarily unavailable,
the RSS `guid` is used for a provisional fallback; a deterministic link hash is the
last resort. Database uniqueness on `(source_id, external_id)` makes repeated CAP
polls idempotent. A successful feed is treated as a current snapshot, so records no
longer returned are deactivated; a feed-level failure preserves the prior snapshot.

The adapter accepts only `Actual`, public, non-cancelled, non-expired CAP alerts.
It rejects malformed XML, invalid linked URLs, private/restricted messages, test or
exercise status, empty hazards, and RSS-only fallbacks older than seven days.

The provider integration guide requires ETag-aware polling. When an XML response
supplies an ETag, the adapter sends `If-None-Match` on the next request and reuses
its bounded in-process XML cache on `304 Not Modified`. A process restart performs
a normal request and rebuilds the cache.

## Loose but bounded official-source policy

News and search adapters require a reviewed disaster keyword plus location
evidence. SACHET is intentionally looser because it is a narrowly allowlisted
official alert source:

- a meaningful CAP `event`, such as `Swell Surge Warning`, may establish a hazard
  even if it is absent from the 53-keyword news taxonomy;
- CAP category supplies conservative response needs when no taxonomy default is
  available;
- structured location evidence is applied in this order: CAP geocode/area, issuing
  sender, headline, then the India centroid; and
- a recent RSS summary may remain as an official provisional signal when one CAP
  detail request is temporarily unavailable.

`official` records provenance, not observed impact. An official forecast still
requires operational review before volunteer dispatch.

## Normalized fields

| Portal field | SACHET/CAP source |
|---|---|
| Stable ID | CAP `identifier`, then provisional RSS `guid`, then link hash |
| Title | English `headline`, CAP `event`, then RSS title |
| Description | CAP `description` plus `instruction` |
| Hazard | 53-keyword canonical type, then normalized official CAP event |
| Severity | CAP `Extreme` 5, `Severe` 4, `Moderate` 3, `Minor`/`Unknown` 2 |
| Location | Inline CAP geometry, external polygon, structured area/geocode, sender/headline gazetteer, then India centroid |
| Time | CAP `sent`, `effective`, `onset`, then RSS `pubDate` |
| Trust | `source_kind=official`, `verification_status=official` |
| Provenance URL | Exact linked SACHET CAP document |
| Needs | Text/taxonomy needs, then conservative CAP-category defaults |

The India centroid is only a last-resort visualization coordinate. Operators should
use the CAP area and geocode evidence for decisions and never interpret the fallback
point as the centre of an affected zone.

## Verify

Deterministic tests do not call the provider:

```powershell
cd backend
python -m pytest tests\test_sachet_adapter.py tests\test_database_migrations.py -q
```

For a reviewed live check, enable live adapters, start the API, select
`sachet-india` from `GET /api/sources`, and run only that source through
`POST /api/ingestion/run`. A successful zero-result run is valid when all provider
items are expired, cancelled, malformed, or otherwise inactive.
