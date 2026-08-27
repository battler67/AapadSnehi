# Adapter development guide

AapadSnehi adapters translate provider-specific responses into `IncidentCandidate` records. Once an adapter returns that contract, the shared ingestion service handles source provenance, validation, deduplication, priority scoring, persistence, dashboard display, map display, and per-source run status.

## Add an adapter

1. Create a module under `backend/app/adapters/`.
2. Subclass `BaseAdapter` and decorate the class with `@register_adapter("provider_key")`.
3. Implement `async fetch(source: Source) -> list[IncidentCandidate]`.
4. Import the adapter class in `backend/app/adapters/__init__.py` so registration occurs at application startup.
5. Add a source record in `SOURCE_SEEDS`, or create an approved source through an administrative workflow.
6. Add fixture-based contract tests that do not require provider credentials or network access.

Minimal shape:

```python
from app.adapters.base import BaseAdapter
from app.adapters.registry import register_adapter


@register_adapter("provider_key")
class ProviderAdapter(BaseAdapter):
    async def fetch(self, source):
        payload = await self.get_json(source.endpoint)
        return [to_incident_candidate(item) for item in payload.get("items", [])]
```

The registry rejects duplicate keys. `get_json`, `post_json`, and `get_text` all use the shared 12-second timeout, refuse redirects, identify the client, and stop responses above 4 MiB. `request_with_metadata` exposes response status and headers for provider protocols such as conditional ETag requests while preserving the same bounds. Provider modules should additionally validate their endpoint before sending credentials or making requests.

## Snapshot and append-only sources

The default adapter behavior is append/update: records not present in a later response remain active. This suits event feeds whose bounded response is not a complete current snapshot.

Set `snapshot_mode = True` for current-result sets such as web search and RSS headlines. After a successful fetch, incidents previously returned by that source but absent from the new normalized result set become inactive. A provider failure never deactivates prior records.

## Search and news trust

Web pages and news aggregators are discovery sources, not warning authorities. Their adapters must use:

```python
source_kind="search"  # or "news"
verification_status="unverified"
```

The shared `normalize_article` function rejects entries without both a recognized disaster type and usable location evidence. The present implementation uses a transparent 53-keyword taxonomy and an India-focused gazetteer; it is intentionally conservative.

## Disaster keyword taxonomy

The reviewable source of truth is `backend/app/data/disaster_keywords.json`. It contains exactly 53 unique phrases mapped to 14 canonical hazard types:

- flood, earthquake, landslide, cyclone, storm and heavy rain;
- wildfire, heatwave and drought;
- tsunami, volcano, avalanche and cold wave;
- structural infrastructure failure.

Phrase matching is case-insensitive, accepts spaces or hyphens, respects word boundaries, and recognizes common final suffixes such as plural `s`/`es`, `-ed`, and `-ing`. Longer phrases are evaluated first. This allows `flooding`, `earthquakes`, `landslides`, `thunderstorms`, and `heavy rains` without making short substrings such as `storm` inside `brainstorming` match.

Each hazard also declares conservative `default_needs` using the portal's allocation vocabulary: `food`, `water`, `shelter`, `medical`, `rescue`, and `transport`. Explicit needs extracted from article text come first, followed by missing hazard defaults. The volunteer-suggestion endpoint already compares these needs with volunteer services/skills, then combines capability fit with distance, availability, and urgency.

The application fails fast when the file is missing, malformed, duplicated, contains unsupported allocation needs, or differs from the required count. When intentionally changing the taxonomy, update the file, declared count, loader constant, tests, and implementation record together.

Keyword coverage is broad but finite. It must not be described as detecting every possible disaster, language, euphemism, or emerging event. Provider results remain unverified until corroborated.

## Included web and RSS adapters

### Serper web search

- Adapter key: `serper`
- Reviewed endpoint: `https://google.serper.dev/search`
- Credential: `AAPAD_SERPER_API_KEY`
- Query scope: recent India-focused disaster terms
- Result policy: request a wider result set, preserve provider ranking, reject non-disaster or unlocated entries, and return at most five
- Provider reference: [Serper](https://serper.dev/)

The credential is sent only to the exact reviewed HTTPS host and path. Never put a real key in `.env.example`, source code, fixtures, screenshots, or documentation.

### Google News RSS

- Adapter key: `google_news`
- Allowed host: `https://news.google.com/rss...`
- Credential: none
- Result policy: parse RSS/Atom entries in feed order, normalize plain text, reject non-disaster or unlocated entries, and return at most five per configured feed

Configured feeds:

- `https://news.google.com/rss?hl=en-IN&gl=IN&ceid=IN:en`
- `https://news.google.com/rss/search?q=artificial+intelligence&hl=en-US&gl=US&ceid=US:en`
- `https://news.google.com/rss/search?q=India+technology&hl=en-IN&gl=IN&ceid=IN:en`

The AI and technology feeds are intentionally passed through the same disaster/location filter. It is valid for either feed to produce zero incidents.

### SACHET India CAP RSS

- Adapter key: `sachet`
- Reviewed host: `https://sachet.ndma.gov.in`
- Credential: none
- Source: the single official `rss_india.xml` feed
- Schedule: `AAPAD_SACHET_POLL_SECONDS`, default `300`; active only with live adapters enabled, `0` disables polling
- Result policy: at most 200 national RSS items, eight concurrent CAP item operations, CAP-first normalization, official-event and lifecycle filtering, inline/external geometry parsing, and current-snapshot retirement
- Provider references: [SACHET CAP feed](https://sachet.ndma.gov.in/CapFeed), [agency integration guide](https://sachet.ndma.gov.in/docs/Integration_Guide_For_Agencies.pdf)

SACHET is deliberately looser than article normalization because the input is already an allowlisted official alert feed. A meaningful CAP event can establish the hazard even when it is absent from the 53 English news phrases. The adapter remains strict about source URLs, `Actual` status, public scope, cancellation, expiry, response bounds, and stable provenance. Linked CAP failures can use a recent RSS item as a temporary fallback; arbitrary RSS sources do not receive this policy.

The adapter sends `If-None-Match` after observing an ETag and reuses its bounded in-process XML cache on `304 Not Modified`. The same persistent HTTP client is used for one RSS/CAP/polygon run. Full polling, parsing, migration, and fallback behavior is documented in [SACHET CAP adapter](sachet-cap-adapter.md).

### Bluesky helper search

- Adapter key: `bluesky`
- SDK/service: `atproto.Client` against the default `https://bsky.social` service
- Credential: backend-only `AAPAD_BLUESKY_EMAIL` and `AAPAD_BLUESKY_APP_PASSWORD`
- Default query/limit: `floods in india`, at most 10 posts
- Result policy: recognized disaster term plus an explicit help offer; requests and negations are excluded; authors are deduplicated by DID

The `/bluesky-helpers` page invokes the adapter through the token-free quick-demo `POST /api/bluesky/scan` route and displays the returned public author IDs. The provider credential remains backend-only. This is deterministic keyword matching, not model inference or sentiment analysis. Results are not persisted and no Bluesky write action is implemented. See [Bluesky helper adapter](bluesky-helper-adapter.md).

## Local verification

Run deterministic adapter tests:

```powershell
cd backend
python -m pytest tests\test_news_adapters.py -q
python -m pytest tests\test_sachet_adapter.py -q
python -m pytest tests\test_bluesky_adapter.py tests\test_bluesky_api.py -q
```

For a reviewed live environment, set variables before API startup:

```powershell
$env:AAPAD_ENABLE_LIVE_ADAPTERS="true"
$env:AAPAD_SERPER_API_KEY="<rotated-provider-key>"
python -m uvicorn app.main:app --reload --port 8000
```

Then use **Refresh live signals** on the pipeline page, or call:

```powershell
Invoke-RestMethod -Method Post `
  -Uri http://localhost:8000/api/ingestion/run `
  -ContentType "application/json" `
  -Body '{"source_ids":[],"live":true}'
```

The dashboard exposes up to five active external incidents after a successful run. Repeat the run to verify source-scoped deduplication and snapshot retirement.
