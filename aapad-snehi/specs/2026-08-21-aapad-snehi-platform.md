# AapadSnehi disaster-response platform

Date: 2026-08-21
Branch: `feature/aapad-snehi-platform`
Scope: new sibling project at `aapad-snehi/`; `mind-masker/` is a read-only visual reference.

## Product outcome

Build a runnable, responsive MVP that turns multiple disaster signals into a common incident model, visualizes recent events on a time-filtered heat map, accepts camera/photo reports from citizens, registers volunteers and their services, and gives an administrator an explainable priority queue for assigning responders.

## Boundaries

- Reuse only visual ideas from the reference: dark navy surfaces, cyan/violet accents, glass panels, rounded geometry, restrained glow, display/body/mono typography, and responsive spacing.
- Do not copy reference application components, domain logic, routes, text, branding, or redaction behavior.
- Official alerts, media-derived signals, and community reports must retain provenance and must never be presented as equivalent. Citizen submissions start as `unverified`.
- Public warning publication is limited to authoritative sources. News/search feeds are operational signals for review, not official warnings.
- Live providers are optional and may fail independently. The local demo remains usable with clearly labelled seeded data.
- Uploaded images are evidence, not public content. Validate type/size and keep storage replaceable by an object-store adapter.
- The admin experience is a demonstration console, not production authentication. Production deployment requires OIDC/RBAC, audit retention, malware scanning, rate limits, and consent/privacy review.

## Architecture

### Current runnable MVP

- Frontend: React + TypeScript + Vite, direct Leaflet integration, CSS design system, service worker shell cache, and local queued-report fallback.
- API: FastAPI + Pydantic + SQLAlchemy.
- Development persistence: SQLite in `backend/data/` with repository/service boundaries.
- Evidence: local upload directory in development.
- Ingestion: synchronous, bounded batches with timeouts, deduplication, per-source run records, and normalized provenance.

### Production target

- PostgreSQL + PostGIS for transactional incident/volunteer data, spatial indexes, radius/containment queries, and model-ready feature history.
- S3-compatible object storage for photos; database stores only metadata and object keys.
- Celery workers with Redis or RabbitMQ when ingestion, image verification, geocoding, and ML inference become durable/heavy jobs.
- FastAPI remains the public API and model-serving seam; trained models and features are versioned separately from operational records.

## Ingestion pipeline

`source adapter -> raw envelope -> portal normalizer -> validation -> deduplication -> trust classification -> priority features -> incident store`

Included adapters:

1. USGS earthquake GeoJSON feed: direct geospatial hazard observations.
2. NASA EONET v3: curated near-real-time natural-event metadata.
3. ReliefWeb latest reports: humanitarian/disaster articles; requires an approved `appname` for live use.
4. GDELT DOC 2.0: disaster-related web/news search.
5. Admin-approved government feed: HTTPS JSON, GeoJSON, RSS, or CAP XML from allowlisted hosts such as IMD/WMO CAP sources.
6. News normalizer: converts article/search records into the common portal schema using transparent keyword classification and a small India gazetteer. Items without adequate location evidence remain review-only.

Every incident stores `external_id`, source name/kind/URL, authority, verification status, observed time, hazard type, severity, coordinates, location text, affected estimate, needs, and an explainable priority score.

## Priority and assignment

Incident priority is a deterministic 0-100 score composed from hazard severity, recency, affected-population estimate, urgent needs, source trust, and response coverage gap. The API returns the score breakdown so administrators can inspect it.

Volunteer suggestions combine service/skill overlap, availability, approximate distance, and incident urgency. Admin allocation is always an explicit action; the algorithm recommends but does not silently dispatch people.

## User journeys

- Operations: filter 24 hours/7/30/90 days, switch hazard types, inspect heat intensity and provenance, and open priority details.
- Citizen: capture or select a photo, add a description/category/severity/location and needs, consent to evidence handling, submit, and receive a tracking ID. Offline failures queue locally for later retry.
- Volunteer: register identity/contact/home location/services/skills/availability, see suitable open missions, and claim an assignment.
- Admin: review ranked incidents, inspect score factors, select an available volunteer, create/dispatch assignments, run adapters, and add an approved government source.
- Pipeline: see source health, normalized-schema contract, run history, and live-versus-demo state.

## Verification

- Backend unit tests for normalization, severity/priority scoring, deduplication, government-source validation, reports, volunteers, and assignment APIs.
- Frontend TypeScript and production build.
- API health check plus a smoke journey covering dashboard, report, volunteer, ingestion, and assignment operations.
- Confirm `mind-masker/` has no tracked or untracked changes caused by this work.

## Research basis

- IMD documents public warning APIs and CAP alerts; the paper specifically highlights district warning colors, SACHET, provenance, crowd reporting, and short-range forecasting limits.
- USGS provides programmatic GeoJSON feeds; NASA EONET v3 provides GeoJSON event geometry and time filtering; ReliefWeb v2 provides curated reports; GDELT DOC 2.0 provides recent full-text news search.
- PostGIS keeps spatial and relational data together with spatial indexes. FastAPI provides typed validation/OpenAPI and a natural Python model-serving boundary. FastAPI background tasks are sufficient for the MVP; durable multi-worker jobs move to Celery.
- OpenStreetMap standard tiles are acceptable for modest interactive development use with visible attribution and no offline tile prefetching; production must configure a suitable provider or self-hosted tiles.

## Implementation record

Completed on branch `feature/aapad-snehi-platform` as a separate `aapad-snehi/` project.

Major edits:

- Added FastAPI/SQLAlchemy service with SQLite development persistence, upload validation, provenance-aware incident model, explainable priority scoring, volunteer fit scoring and assignment workflows.
- Added bounded USGS, EONET, ReliefWeb, GDELT, generic government/CAP and deterministic seed adapters; added article normalization, GeoJSON point/polygon handling, source-specific run history and idempotent deduplication.
- Added React/Vite application with responsive operations, map, citizen report, volunteer, admin and pipeline pages; added Leaflet heat layer, API/demo fallback, IndexedDB report queue and same-origin service-worker shell cache.
- Added architecture/research decision record, provider citations, live-adapter configuration and production-hardening boundaries.
- Preserved `mind-masker/` without modifications; its pre-existing untracked `docs/Research_ps.pdf` remains the research input.

Verification completed:

- `python -m pytest`: 21 passed.
- `npm test`: 4 passed across 2 files.
- `npm run build`: TypeScript and Vite production build passed; 1,731 modules transformed, 126.57 kB gzip JavaScript.
- API smoke: `/health` returned `ok`/`connected`; dashboard returned 7 incidents and 4 available volunteers; 30-day heatmap returned 7 points.
- Route smoke: `/`, `/map`, `/report`, `/volunteer`, `/admin`, and `/pipeline` returned HTTP 200 from Vite.
- Browser renders: desktop operations and admin pages rendered in headless Chrome; admin showed `API online`. A narrow report-page render confirmed the responsive form breakpoint.
- Credential scan found no credential-shaped values; matches were only Python's `secrets` module and URL credential rejection logic.
