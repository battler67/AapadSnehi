# AapadSnehi

A new, standalone disaster-response coordination project. It uses the visual character of the adjacent `mind-masker` reference—dark navy, cyan/violet accents, glass panels and compact operational typography—but none of that project's components, routes, text, or redaction logic.

The MVP includes:

- A time-filtered Leaflet disaster heat map with official/corroborated/unverified trust layers.
- Explainable 0–100 response priority using severity, recency, affected estimate, needs, trust and current response coverage.
- A dedicated Users page for citizen camera/photo reporting with safe image preprocessing, OpenAI vision descriptions, independent disaster-keyword confirmation, Cloudinary evidence storage, precise location, moderation status and an IndexedDB offline queue.
- A dedicated Volunteers page for registration with one to five preferred work areas, service/skill profiles, suitable missions, self-claim flow and a shared citizen-image review queue.
- A dedicated Admin page with the priority queue, responder home/preferred-area context, fit suggestions, explicit assignment and dispatch history.
- Preview-and-confirm automatic distribution of an administrator-selected volunteer pool across multiple selected disaster places.
- USGS, NASA EONET, ReliefWeb, GDELT, Serper web search, Google News RSS, SACHET India CAP RSS, Bluesky helper search and admin-approved government feed adapters.
- News-to-portal normalization, deduplication, per-source failures and ingestion run history.
- A reviewable 53-keyword disaster taxonomy with canonical hazard types and response needs for volunteer matching.
- SQLite for zero-infrastructure local development and a documented PostgreSQL/PostGIS production path.

All included incident and volunteer records are clearly labelled demonstration data. The app does not publish citizen or news-derived signals as official warnings.

## Run locally

Requirements: Node.js 22+, npm 11+, and Python 3.11+.

### 1. API

From `backend`:

```powershell
python -m pip install -r requirements.txt
python -m uvicorn app.main:app --reload --port 8000
```

Useful URLs:

- API health: `http://localhost:8000/health`
- OpenAPI: `http://localhost:8000/docs`

### 2. Web app

From `web` in another terminal:

```powershell
npm install
npm run dev
```

Open the application at `http://localhost:5173`. If the API is unavailable, the frontend intentionally remains usable with deterministic demo data and marks the header `Demo data`.

Audience pages are intentionally public in the current prototype:

- Users and incident reporting: `http://localhost:5173/users`
- Volunteer registration, profile, and missions: `http://localhost:5173/volunteers`
- Administration and dispatch: `http://localhost:5173/admin`

The former `/report` and `/volunteer` paths are retained as client-side aliases. This route separation is information architecture only; login and RBAC are intentionally outside the current scope.

## Live adapter mode

The safe default is deterministic/no-credential operation. To permit external provider requests for a reviewed local environment:

```powershell
$env:AAPAD_ENABLE_LIVE_ADAPTERS="true"
$env:AAPAD_RELIEFWEB_APPNAME="your-approved-app-name"
$env:AAPAD_SERPER_API_KEY="your-rotated-provider-key"
$env:AAPAD_SACHET_POLL_SECONDS="300"
$env:AAPAD_BLUESKY_EMAIL="your-bluesky-email"
$env:AAPAD_BLUESKY_APP_PASSWORD="your-bluesky-app-password"
python -m uvicorn app.main:app --reload --port 8000
```

Then use **Refresh live signals** on the pipeline page or call `POST /api/ingestion/run` with `{"source_ids": [], "live": true}`. ReliefWeb requires a pre-approved app name. Serper returns at most five India-focused results after disaster and location filtering. Google News RSS uses the configured India headlines, AI and India technology feeds; unrelated entries are discarded. SACHET parses the single national `rss_india.xml` feed, follows each linked CAP document, and excludes cancelled, non-public, test/exercise, and expired alerts. Provider failures are recorded independently and do not stop other adapters.

The dedicated **Bluesky helpers** page at `http://localhost:5173/bluesky-helpers` runs the notebook-style `atproto` provider search on the server. Open the page, enter a query, and select **Run Bluesky scan**—the quick demo has no portal sign-in or role gate. The server searches at most `AAPAD_BLUESKY_MAX_POSTS` public posts (default `10`) and displays unique author DIDs/handles only when the post contains a recognized disaster term and an explicit offer-to-help phrase. It uses deterministic keywords—no Hugging Face, Transformers, model download, sentiment score, automated contact, or volunteer registration. Put the separate Bluesky provider credentials in the ignored `.env`, not in source or the notebook; use a Bluesky app password and rotate the credential already exposed in the notebook before reuse.

Search and news results remain unverified operational signals. SACHET records retain official CAP provenance; that trust label does not mean a forecast has already caused damage or that volunteers should be dispatched without operational review. A successful refresh places up to five current external incidents on the dashboard. Search/news items must match the 53-keyword disaster taxonomy and contain usable location evidence, while SACHET can also use a meaningful official CAP event plus its state context. Detected hazards add conservative default response needs so the existing allocation endpoint can rank volunteers by capability, availability, distance, and urgency. Keep real provider credentials out of source and `.env.example`.

Volunteer registration requires one to five preferred work areas, separated with semicolons in the web form so city/state commas remain intact. These areas are visible on the volunteer profile and beside responder suggestions in the admin allocation view. They are operational context only: availability, capability, distance, incident conditions, and the administrator's explicit dispatch decision still govern assignments. Existing SQLite volunteer records receive their home location as the legacy default.

Government feeds added through the admin page must use HTTPS and a host in `AAPAD_GOVERNMENT_HOSTS`. The backend rejects credential-bearing URLs, loopback/private IP literals and unapproved hosts. Review provider terms, attribution and rate limits before enabling a new feed.

When live adapters are enabled, the backend runs the national SACHET source once at startup and then every `AAPAD_SACHET_POLL_SECONDS` seconds (default `300`; set `0` to disable scheduled polling). This is an RSS/CAP parser, not a crawler: it knows the exact national feed and validates every linked CAP and polygon URL before fetching it. CAP `identifier` is the source-scoped deduplication key. The adapter also implements ETag/`304` caching for fetched SACHET XML resources. See [SACHET CAP adapter](docs/sachet-cap-adapter.md) for lifecycle, geometry, fallback, and operating details.

## Image screening and evidence storage

Citizen evidence is screened by `gpt-4.1-mini` through the OpenAI Responses API and
stored as authenticated Cloudinary media. Inference stays hosted; this project does
not install or cache model weights, Torch, or Transformers:

```powershell
$env:OPENAI_API_KEY="your-backend-only-key"
$env:OPENAI_VISION_MODEL="gpt-4.1-mini"
$env:CLOUDINARY_KEY="cloudinary://api_key:api_secret@cloud_name"
python -m uvicorn app.main:app --reload --port 8000
```

Alternatively set all of `CLOUDINARY_CLOUD_NAME`, `CLOUDINARY_API_KEY`, and
`CLOUDINARY_API_SECRET`. A single bare key is insufficient for signed upload and
deletion. The backend loads the ignored root `.env`; process variables win.

Automatic acceptance requires OpenAI's visible evidence, the existing 53-keyword
policy, and the reporter-selected hazard to agree, with the original safely stored
in Cloudinary. Every other result becomes `Volunteer review needed`; OpenAI never
automatically rejects a report. Pending reports and their images appear in both the
Volunteer and Admin pages. Volunteer rejection deletes the Cloudinary/local image
before the rejection is saved. Accepted reports remain community evidence labelled
`AI screened`, never `official` or `corroborated`.

The inference request uses a bounded metadata-free JPEG and `store: false`. The
hourly call limit is a process-local demo safeguard, not a distributed spending
guarantee. The retained Hugging Face/Qwen and BLIP code is inactive until suitable
account capability is available. See [Image report triage](docs/image-report-triage.md)
and the historical [image model evaluation](docs/image-model-evaluation.md).

## Verify

```powershell
cd backend
python -m pytest

cd ..\web
npm test
npm run build
```

Current verified baseline:

- Backend: 202 tests.
- Frontend: 11 tests.
- TypeScript and Vite production build.

## Important limitations

- The User, Volunteer, and Admin routes have no login or RBAC in this prototype. The Admin page is a demonstration console, not an authorization boundary; add agency identity, audited roles, and approval policy before a real deployment.
- Review images use authenticated Cloudinary delivery or a private local fallback, but the prototype has no identity/RBAC; add authenticated roles, malware scanning, audit logs, and retention rules before production.
- The priority formula is decision support, not a prediction of casualties or a substitute for incident command.
- The built-in OpenStreetMap tile URL is for modest interactive development. It has visible attribution and the service worker never prefetches map tiles. Configure a suitable provider or self-hosted tiles before scale/offline use.
- Hosted vision screening does not establish image authenticity, location, recency, causation, or disaster severity. It is advisory screening with a recorded provider/model/prompt/evidence trail and human override, not official verification.

See [Architecture and research](docs/architecture-and-research.md) for provider choices, production topology and the AI/ML path. See [Adapter development](docs/adapter-development.md) for the registry contract, disaster taxonomy, trust rules, snapshot behavior, and extension steps. See [Bluesky helper adapter](docs/bluesky-helper-adapter.md) for credential setup, intent rules, and the scan page. See [SACHET CAP adapter](docs/sachet-cap-adapter.md) for national polling and CAP parsing. See [Image report triage](docs/image-report-triage.md) for image screening, failure behavior, moderation, privacy, and provider replacement.
See [Volunteer allocation strategies](docs/allocation-strategies.md) for the default distribution formula, preview/confirmation contract, safety invariants, and instructions for registering a replacement algorithm.
