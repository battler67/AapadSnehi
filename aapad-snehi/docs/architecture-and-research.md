# Architecture and research

This decision record combines the requested product scope with the themes in the local research paper: hyper-local hazards, IMD/NDMA/SACHET authority, citizen observations, low connectivity, trusted-volunteer verification, severity colours, location subscriptions and the principle that public warnings should come from authentic government agencies.

## Recommendation

Use **FastAPI + PostgreSQL/PostGIS** as the long-term operational core.

- FastAPI keeps request and adapter validation typed, generates OpenAPI documentation, supports async I/O, and uses ordinary Python types. That is also the lowest-friction boundary for later PyTorch/TensorFlow inference services. [FastAPI features](https://fastapi.tiangolo.com/features/)
- PostgreSQL handles transactional relationships among incidents, sources, reports, volunteers, assignments, audit events and model versions.
- PostGIS keeps spatial and relational data in the same transaction and adds spatial types, indexes, distance/containment functions, clustering and GeoJSON exchange. That directly fits heat maps, nearby-volunteer searches, district boundaries and route-impact overlays. [PostGIS introduction](https://postgis.net/docs/manual-3.7/en/postgis_introduction.html)
- Store citizen photos in S3-compatible object storage; keep only the object key, hash, media metadata, consent/retention fields and moderation state in PostgreSQL.
- Start ingestion as bounded FastAPI tasks for the MVP. Move scheduled feeds, retries, image checks and model inference to Celery workers with Redis or RabbitMQ when they require multiple processes/servers. FastAPI explicitly recommends a larger tool such as Celery for heavy background computation, and Celery provides distributed workers and scheduling. [FastAPI background-task guidance](https://fastapi.tiangolo.com/tutorial/background-tasks/), [Celery documentation](https://docs.celeryq.dev/en/stable/)

SQLite is deliberately used only for the current local MVP so a reviewer can run it without Docker or cloud credentials. SQLAlchemy keeps that development choice behind a database boundary. The production migration should add Alembic migrations, `geography(Point, 4326)` columns and GiST indexes, then replace application-side Haversine ranking with PostGIS distance queries.

### Why not MongoDB as the primary store?

Source payloads are document-shaped, but the operational system is dominated by transactions and relationships: one incident has provenance and reports; assignments must uniquely connect an incident and volunteer; role/audit constraints matter; and spatial joins against administrative boundaries will be routine. Raw provider envelopes can still live in object storage or a JSONB staging table. A second primary document database would increase operational complexity without improving the main workflows.

### Why not a time-series database first?

Weather grids and sensor observations may later justify TimescaleDB or a lakehouse, but the present product stores discrete incidents, reports and decisions. PostgreSQL/PostGIS is sufficient now. High-volume rasters, forecast cubes and training datasets should be versioned in object storage rather than forced into the incident database.

## Adapter selection

| Need | Adapter | Operational role | Trust handling |
|---|---|---|---|
| Direct hazard observations | USGS significant-earthquake GeoJSON | Global earthquake point/time/magnitude records | Official observation. USGS states its GeoJSON feed is intended as a programmatic interface. [USGS GeoJSON format](https://earthquake.usgs.gov/earthquakes/feed/v1.0/geojson.php) |
| Curated natural events | NASA EONET v3 | Open/closed events, categories, dates and GeoJSON points/polygons | Official/curated signal; retain EONET's underlying source link. [NASA EONET v3](https://eonet.gsfc.nasa.gov/docs/v3) |
| Latest disaster/humanitarian articles | ReliefWeb v2 reports | Curated reports and updates for review | Corroborated operational signal, never auto-published as a warning. Live use requires a pre-approved `appname` from November 2025. [ReliefWeb API](https://apidoc.reliefweb.int/index.html), [report endpoints](https://apidoc.reliefweb.int/endpoints) |
| Web/news search | GDELT DOC 2.0 | Recent disaster-related article discovery | Unverified until an official source or reviewer corroborates it. [GDELT DOC API](https://blog.gdeltproject.org/gdelt-doc-2-0-api-debuts/) |
| India-focused web search | Serper Search API | Ranked recent disaster-page discovery, capped at five normalized results | Unverified; API rank does not make a result authoritative. Credential remains server-side. [Serper](https://serper.dev/) |
| News discovery | Google News RSS | India headlines plus the requested AI and India technology feeds, filtered for disaster and location evidence | Unverified; aggregator inclusion is not corroboration and zero accepted items is valid. |
| India CAP alerts | SACHET national RSS + linked CAP 1.2 | Current warnings across India with event, severity, lifecycle, instructions, area, geocode, and geometry evidence | Official alert provenance from NDMA/SACHET and the issuing agency; forecast certainty and official status do not prove observed impact. [SACHET CAP feed](https://sachet.ndma.gov.in/CapFeed), [ETag integration guide](https://sachet.ndma.gov.in/docs/Integration_Guide_For_Agencies.pdf) |
| Public disaster help offers | Server-side Bluesky search with `atproto` | Bounded, on-demand discovery of public author DIDs/handles whose own post explicitly offers disaster help | Unverified social lead only; deterministic keywords are not proof of identity, availability, capability, or consent. Results are not persisted. |
| Indian official warnings | Admin-approved government adapter | JSON, GeoJSON, RSS and CAP XML from approved institutions | Official only because the admin records the authority and the host passes an allowlist. IMD documents public APIs, district warning colour codes and current CAP alerts. [IMD API portal](https://mausam.imd.gov.in/responsive/apis.php), [current IMD API reference](https://api.imd.gov.in/public/api_reference.html) |

The generic government adapter does not make an arbitrary URL authoritative. Approval is represented by an explicit source record, legal authority, fixed HTTPS host allowlist and provenance on every normalized incident. The dedicated SACHET adapter is narrower: only the official national RSS path and same-host linked CAP/polygon paths are accepted. It follows the provider's ETag protocol, selects a preferred English CAP block where available, rejects inactive lifecycle states, and parses inline or linked geometry before using structured area evidence and the India fallback. DNS-level rebinding protection and egress proxy rules should be added in production; the MVP already rejects private/local IP literals and provider redirects.

## Common event contract

Adapters emit one validated candidate shape:

```text
external provider ID
title + description
hazard type + 1..5 severity
latitude + longitude + human location
observed time
source kind + verification status + source URL
affected estimate + urgent needs
```

The ingestion service then:

1. Records a source-specific run.
2. Validates and bounds the provider response.
3. Normalizes provider categories and timestamps.
4. Rejects article/search items without both hazard and usable location evidence; trusted SACHET items may instead use an official CAP event and structured national-feed context.
5. Deduplicates on `(source_id, external_id)` and refreshes existing records idempotently.
6. Computes an explainable priority breakdown.
7. Stores per-source health without allowing one failed provider to halt the batch.

Adapter discovery is registry-based: a provider subclasses the bounded base adapter, declares a unique adapter key, and returns the common candidate contract. Search/RSS adapters use snapshot mode so successfully refreshed result sets deactivate stale records; failed fetches retain the prior snapshot. Implementation and test conventions are documented in [Adapter development](adapter-development.md).

News conversion intentionally uses a versioned, reviewable 53-keyword taxonomy and a small India gazetteer in this MVP. The taxonomy maps phrases to canonical hazards and conservative response needs so detected incidents can enter the existing volunteer-fit ranking. Matching still requires location evidence, and news/search provenance remains unverified. A future NLP model can suggest entities and coordinates, but its confidence, version and evidence must be stored; uncertain items remain in review and off the operational map.

## Priority and volunteer matching

The incident score is capped at 100:

| Factor | Maximum | Purpose |
|---|---:|---|
| Hazard severity | 40 | Keeps measured/declared intensity dominant |
| Recency | 20 | Exponential decay over roughly three days |
| Affected estimate | 15 | Log scale prevents large estimates from overwhelming all factors |
| Urgent needs | 10 | Adds breadth of required support |
| Source trust | 10 | Official 10, corroborated 7, community reviewed 5, AI screened 3, unverified 2 |
| Response coverage gap | 5 | Falls as volunteers are assigned |

This is an inspectable queue heuristic, not a learned risk model. Admins see every factor and explicitly dispatch a volunteer.

Volunteer fit combines registered service/skill overlap, approximate distance, availability and incident urgency. Registration also records one to five normalized, human-readable preferred work areas. Those preferences are shown to the volunteer and administrator as dispatch context but deliberately do not alter the MVP score: free-form place names require authoritative geocoding and policy-aware containment before they can become a reliable ranking input. In production, PostGIS should pre-filter candidates within a policy radius, and a routing provider should estimate travel time only when road conditions and provider terms are suitable. Preferences never prove current availability, training, jurisdiction, or field safety, and volunteers must never be auto-dispatched into an unsafe area.

Multi-place distribution uses a replaceable strategy registry and persistence-neutral problem/plan contract. The default balanced-greedy strategy operates only on administrator-selected incidents and volunteers, gives coverable uncovered locations an initial pass, then applies a demand-scaled load penalty to the existing explainable fit. A fingerprinted preview must be explicitly confirmed before the batch is stored atomically; a state change invalidates that preview. The complete formula, API, invariants, limitations, and replacement procedure are documented in [Volunteer allocation strategies](allocation-strategies.md).

## Audience routes and access boundary

The frontend separates community users (`/users`), volunteers (`/volunteers`), and administrators (`/admin`) so each audience sees a focused workflow. Citizen evidence submission belongs to Users; responder registration, profile, and mission claiming belong to Volunteers; prioritization and dispatch belong to Admin. Legacy `/report` and `/volunteer` URLs canonicalize to the new routes.

This separation does not currently enforce identity or permissions. Per the prototype scope, there is no login or RBAC, and the Admin route remains a demonstration workspace. A production rollout must treat frontend paths as navigation only and enforce identity, roles, approval policy, and audit logging on backend operations.

## Heat map and low-connectivity design

Leaflet renders an actual weighted heat layer plus severity points. Time windows are applied to occurred timestamps, and trust/hazard filters remain visible. Map tiles use the standard OpenStreetMap endpoint only for modest interactive development with visible attribution. OSM's policy forbids tile prefetch/offline downloads and describes the service as best-effort, so production or offline deployments need a provider that allows the intended load/use or self-hosted tiles. [OpenStreetMap tile policy](https://operations.osmfoundation.org/policies/tiles/)

The service worker caches same-origin application shell resources only; it does not cache or prefetch OSM tiles. Citizen reports that fail to send are stored in IndexedDB with their photo and retried after an `online` event. Future field mode should add an encrypted, user-visible queue, explicit storage duration and conflict/retry controls.

## AI/ML and deep-learning path

Keep ML advisory and versioned:

1. Store immutable raw-provider object keys/hashes and normalized snapshots.
2. Add a feature table keyed by incident, feature timestamp and feature-pipeline version.
3. Train outside the request-serving database from consented/de-identified snapshots.
4. Register model version, input schema, calibration data, geography/time validity and evaluation metrics.
5. Serve inference behind a typed adapter in FastAPI or a separate model service.
6. Write predictions with confidence and model version; never overwrite observed severity or official authority fields.
7. Monitor drift by hazard, region, season and source; preserve a deterministic fallback.

The hosted image seam uses `gpt-4.1-mini` through OpenAI's Responses API rather than loading a model on the local API host. It returns a constrained description, visible-evidence value, canonical hazards, and observations. Automatic acceptance requires OpenAI, the independent 53-keyword/damage policy, and the reporter-selected hazard to agree, with the original stored as authenticated Cloudinary media. Every other result escalates to volunteer review; the model never auto-rejects. Rejection deletes the stored evidence before the state is committed. Provider, model, prompt version, evidence, decision, and reason are persisted, and accepted output receives only an `ai_screened` community label. The Hugging Face/Qwen implementation is retained but inactive. Details and replacement boundaries are documented in [Image report triage](image-report-triage.md), with alternatives in [Image model evaluation](image-model-evaluation.md).

Good next models are duplicate/corroboration detection, image-quality checks, needs extraction and demand forecasting. Do not use captioning for autonomous dispatch or official public warnings. Citizen images may contain faces, homes and location metadata; training use requires a separate lawful basis, minimization, retention and consent design.

## Production hardening backlog

- Agency OIDC/SSO, granular RBAC, step-up approval for public warnings and append-only audit logs.
- Alembic migrations; PostgreSQL/PostGIS; connection pooling; spatial indexes and backup/restore drills.
- Private object storage, signed upload/download URLs, antivirus/image decoding, EXIF policy and lifecycle deletion.
- API rate limits, abuse/spam scoring with an appeal path, CAPTCHA where appropriate, and contact verification.
- Network egress allowlist/proxy, DNS rebinding defense, provider-specific rate/backoff/caching policy and raw-envelope retention.
- Celery worker queues separated by ingestion, media and model workload; idempotency keys and dead-letter review.
- Multilingual content, accessible warning presentation, subscription consent and delivery-provider integration.
- Offline-capable map provider or self-hosted vector tiles; do not prefetch standard OSM tiles.
- Observability for adapter freshness, normalization rejects, geocoding uncertainty, queue lag and dispatch acknowledgement.
