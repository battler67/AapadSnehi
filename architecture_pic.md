# AapadSnehi — Portal Architecture

Source-verified on **16 September 2026**. Scope: the current local `aapad-snehi/`
application, including the unified flood reporting and optional OpenAI photo review.
These Mermaid diagrams render in compatible Markdown viewers, including GitHub.

**Color key:** blue = browser/user interfaces; green = backend processing;
purple = storage; orange = external providers; rose = security/review boundaries.
Labels remain authoritative; colors are visual aids, not verification indicators.

**Reading guide:** solid arrows show implemented paths; dotted arrows show optional,
configuration-dependent connections. An implemented adapter does not imply a live,
configured or verified external service. The application is a **modular monolith**,
not a collection of separately deployed microservices.

## 1. Complete system overview

```mermaid
flowchart TB
    Citizen["Citizen / reporter"]
    Public["Public viewer"]
    Coord["Authorized flood coordinator"]
    Responder["Authorized flood responder"]
    DemoUser["Prototype operator / volunteer"]

    subgraph Browser["Browser — React + TypeScript + Vite"]
        Shell["Shared navigation and route handling"]
        ReportUI["Flood report wizard<br/>Optional photos, location, situation, receipt"]
        FloodUI["Flood operations<br/>Map, list, filters, summaries, incident detail"]
        GeneralUI["Overview, risk map, volunteers,<br/>admin and ingestion pipeline"]
        SocialUI["Bluesky Helpers<br/>Public help-offer leads"]
        EdgeUI["Edge warning lab<br/>Simulations and risk events"]
        SafetyUI["Disaster Safety<br/>Guidance content"]
        Local["IndexedDB flood drafts<br/>Photo blobs and retry state"]
        SW["Service worker / app-shell cache<br/>No private API or media caching"]
        Leaflet["Leaflet maps<br/>Points, heatmap and flood clusters"]
        Client["Typed HTTP clients<br/>JSON requests and multipart photos"]
        Shell --> ReportUI & FloodUI & GeneralUI & SocialUI & EdgeUI & SafetyUI
        ReportUI <--> Local
        SW --> Shell
        FloodUI & GeneralUI & EdgeUI --> Leaflet
        ReportUI & FloodUI & GeneralUI & SocialUI & EdgeUI --> Client
    end

    Citizen --> ReportUI
    Public --> FloodUI
    Coord & Responder --> FloodUI
    DemoUser --> GeneralUI

    subgraph Server["One Python backend — FastAPI + Pydantic + Uvicorn"]
        API["HTTP API<br/>Validation, CORS, health and OpenAPI docs"]
        Guard["Flood-only access controls<br/>Reporter keys, role, city scope, assigned team"]
        Flood["Flood reporting and operations service"]
        Media["Private upload validation<br/>Pillow decoding, resizing, metadata removal"]
        Vision["Shared OpenAI image client<br/>Bounded concurrency and hourly calls"]
        Ingest["Adapter registry and ingestion<br/>Normalization, deduplication, provenance"]
        Allocation["General priority and volunteer allocation<br/>Explainable scoring, preview and confirmation"]
        Bluesky["Bluesky adapter<br/>Post search and rule-based help-intent matching"]
        Edge["Edge simulation and risk pipeline"]
        ORM["SQLAlchemy persistence<br/>Transactions and flood version checks"]
        API --> Guard --> Flood
        Flood --> Media --> Vision
        API --> Ingest & Allocation & Bluesky & Edge
        Flood & Media & Ingest & Allocation & Edge --> ORM
        Bluesky --> Ingest
    end

    Client --> API
    ORM --> DB[("SQLite database<br/>WAL and busy timeout")]
    API --> LegacyFiles["Legacy report image storage<br/>Local uploads or configured Cloudinary"]
    Vision -. "Configured; optional uploaded images only" .-> OpenAI["OpenAI Responses API"]
    Ingest -. "Live gate and provider configuration" .-> Feeds["USGS, NASA EONET, government feeds,<br/>SACHET, ReliefWeb, GDELT,<br/>Google News RSS and Serper"]
    Bluesky -. "Backend account / app password" .-> Bsky["Bluesky / AT Protocol"]
    Leaflet -. "Map tiles" .-> OSM["OpenStreetMap or configured tile server"]
    ReportUI -. "Device permission" .-> GPS["Browser geolocation"]
    ReportUI --> EXIF["Local photo GPS suggestion<br/>Requires reporter confirmation"]
    Flood -. "Configured geocoding proxy" .-> Geocode["Nominatim address lookup"]
    LegacyFiles -. "Legacy uploads only" .-> Cloudinary["Cloudinary private image storage"]

    classDef ui fill:#DBEAFE,stroke:#2563EB,color:#172554,stroke-width:2px
    classDef service fill:#DCFCE7,stroke:#16A34A,color:#14532D,stroke-width:2px
    classDef storage fill:#F3E8FF,stroke:#9333EA,color:#581C87,stroke-width:2px
    classDef external fill:#FFEDD5,stroke:#EA580C,color:#7C2D12,stroke-width:2px
    classDef guard fill:#FFE4E6,stroke:#E11D48,color:#881337,stroke-width:2px
    class Citizen,Public,Coord,Responder,DemoUser,Shell,ReportUI,FloodUI,GeneralUI,SocialUI,EdgeUI,SafetyUI,Leaflet,Client ui
    class API,Flood,Media,Vision,Ingest,Allocation,Bluesky,Edge,ORM,EXIF service
    class Local,SW,DB,LegacyFiles storage
    class OpenAI,Feeds,Bsky,OSM,GPS,Geocode,Cloudinary external
    class Guard guard
    style Browser fill:#EFF6FF,stroke:#60A5FA,color:#172554
    style Server fill:#F0FDF4,stroke:#4ADE80,color:#14532D
```

The Bluesky-to-ingestion connection represents the adapter's `fetch()` path.
The dedicated Helpers scan returns leads to the browser; it does **not** register
volunteers, create assignments, or maintain a persistent people database.

## 2. Routes and module ownership

| Browser route | Backend / data responsibility | Access boundary |
|---|---|---|
| `/` | `/api/dashboard`, general incidents, sources and assignments | Public prototype |
| `/map` | General incidents and heatmap | Public prototype; not validated flood extent |
| `/flood/report` | `/api/flood/reports`, receipt lookup, media upload | Creation is public; own-report access requires private reporter key |
| `/flood` | `/api/flood/incidents`, grouping, review, teams and tasks | Coarse public view; operational details require scoped credential |
| `/volunteers` | Volunteer registration, open tasks, claims, assignments | Public prototype, not flood responder authorization |
| `/admin` | Legacy moderation and allocation controls | Public prototype, not an authenticated administrator boundary |
| `/pipeline` | Sources, ingestion runs, live-request controls | Public prototype |
| `/bluesky-helpers` | `POST /api/bluesky/scan` | Public prototype endpoint; provider credentials remain server-side |
| `/edge-early-warning` | `/api/edge/*` | Simulated research/demo workflow, not production RBAC |
| `/safety` | Frontend guidance content | Public |

`/users`, `/user`, and `/report` normalize to `/flood/report` locally. The old
Users component and legacy report APIs remain in the source for compatibility;
Users is no longer a separate navigation entry. Browser requests use REST/HTTP,
not WebSockets or SSE. Flood operations refresh periodically (20 seconds);
the edge snapshot view polls every 2 seconds.

## 3. Citizen report, photo screening and rescue workflow

```mermaid
%%{init: {"theme":"base","themeVariables":{"actorBkg":"#DBEAFE","actorBorder":"#2563EB","actorTextColor":"#172554","actorLineColor":"#64748B","signalColor":"#334155","signalTextColor":"#172554","labelBoxBkgColor":"#DCFCE7","labelBoxBorderColor":"#16A34A","labelTextColor":"#14532D","loopTextColor":"#14532D","noteBkgColor":"#FEF3C7","noteBorderColor":"#D97706","noteTextColor":"#78350F","activationBkgColor":"#F3E8FF","activationBorderColor":"#9333EA"}}}%%
sequenceDiagram
    actor Citizen
    participant UI as Flood report wizard
    participant Draft as IndexedDB
    participant API as Flood API
    participant DB as SQLite
    participant AI as OpenAI (if configured)
    actor Coordinator
    actor Responder

    Citizen->>UI: Select report type; enter location and situation
    UI->>Draft: Save draft and optional compressed photos
    Note over UI,Draft: Offline drafts are not platform receipts
    Citizen->>UI: Confirm pin or supply textual description
    UI->>API: Submit text/location with idempotency key
    API->>DB: Save source report, operational incident and audit
    Note over API,DB: Rescue report also creates a needs-review task
    API-->>UI: Reference, server receipt and review/location status
    alt Optional photos attached
        loop Each photo, maximum four
            UI->>API: Upload photo with private reporter key
            API->>API: Decode actual image and strip derivative metadata
            API->>DB: Commit private media and pending photo review
            API->>AI: Screen derivative only, bounded to 25 seconds
            alt Screening succeeds
                AI-->>API: Caption and visible-evidence assessment
                API->>DB: Store private advisory result and audit
            else Missing config, error or timeout
                API->>DB: Store unavailable status; retain attached photo
            end
            API-->>UI: Attachment status and advisory screening result
        end
    else No photographs
        Note over UI,API: No AI request; report remains usable
    end
    UI->>Draft: Remove completed submitted draft
    Note over UI,Draft: Failed photo uploads remain available for explicit retry
    Coordinator->>API: Review evidence, clarify location, group reports
    API->>DB: Version-checked changes and audit trail
    Coordinator->>API: Set canonical situation, urgency and verification
    Coordinator->>API: Mark task ready; assign a scoped team
    Responder->>API: En route, on scene, outcome and remaining needs
    API->>DB: Persist task transitions and actor/timestamps
    Note over API,DB: Rescue completion does not automatically resolve flooding
```

Photo results are advisory, not authenticity checks or verified depth, headcount,
urgency, or dispatch decisions. Upload retries reuse the same photo hash per report
without repeating screening. A process interruption can leave screening pending:
there is no durable image-job queue or automatic recovery worker.

### Rescue task state machine

```mermaid
stateDiagram-v2
    [*] --> NeedsReview
    NeedsReview --> Ready: Canonical situation reviewed
    NeedsReview --> Cancelled
    Ready --> Assigned: Coordinator selects authorized team
    Ready --> NeedsReview
    Ready --> Cancelled
    Assigned --> Assigned: Explicit reassignment
    Assigned --> EnRoute
    Assigned --> Ready: Unassign / prepare reassignment
    Assigned --> Cancelled
    EnRoute --> OnScene
    EnRoute --> UnableToReach
    EnRoute --> Ready
    EnRoute --> Cancelled
    OnScene --> Resolved: Outcome and remaining needs
    OnScene --> UnableToReach
    OnScene --> Ready
    UnableToReach --> Ready
    UnableToReach --> EnRoute
    UnableToReach --> Cancelled
    Resolved --> NeedsReview: Reopen
    Cancelled --> NeedsReview: Reopen

    classDef review fill:#FEF3C7,stroke:#D97706,color:#78350F,stroke-width:2px
    classDef ready fill:#DBEAFE,stroke:#2563EB,color:#172554,stroke-width:2px
    classDef active fill:#E0E7FF,stroke:#4F46E5,color:#312E81,stroke-width:2px
    classDef complete fill:#DCFCE7,stroke:#16A34A,color:#14532D,stroke-width:2px
    classDef blocked fill:#FFE4E6,stroke:#E11D48,color:#881337,stroke-width:2px
    classDef inactive fill:#F1F5F9,stroke:#64748B,color:#334155,stroke-width:2px
    class NeedsReview review
    class Ready ready
    class Assigned,EnRoute,OnScene active
    class Resolved complete
    class UnableToReach blocked
    class Cancelled inactive
```

These are display labels for the backend states `needs_review`, `ready`, `assigned`,
`en_route`, `on_scene`, `unable_to_reach`, `resolved`, and `cancelled`. The backend
checks both allowed transitions and actor permissions; not every actor can take
every arrow. Task progress, flood status, verification, urgency, and observation
freshness are separate fields.

## 4. Data architecture and privacy boundary

```mermaid
%%{init: {"theme":"base","themeVariables":{"primaryColor":"#F3E8FF","primaryTextColor":"#581C87","primaryBorderColor":"#9333EA","lineColor":"#64748B","tertiaryColor":"#FAF5FF"}}}%%
erDiagram
    SOURCE ||--o{ INCIDENT : provides
    SOURCE ||--o{ INGESTION_RUN : records
    INCIDENT ||--o{ CITIZEN_REPORT : contains
    INCIDENT ||--o| FLOOD_OPERATION : extends
    CITIZEN_REPORT ||--o| FLOOD_REPORT_DETAIL : extends
    INCIDENT ||--o{ FLOOD_REPORT_DETAIL : groups
    FLOOD_PLACE o|--o{ FLOOD_PLACE : parent
    FLOOD_PLACE o|--o{ FLOOD_OPERATION : canonical_location
    CITIZEN_REPORT ||--o{ FLOOD_MEDIA : attaches
    FLOOD_MEDIA ||--o| PHOTO_REVIEW : advisory_result
    INCIDENT ||--o{ RESCUE_TASK : coordinates
    FLOOD_TEAM o|--o{ RESCUE_TASK : assigned_to
    FLOOD_TEAM o|--o{ FLOOD_IDENTITY : membership
    INCIDENT ||--o{ FLOOD_AUDIT : history
    INCIDENT ||--o{ LEGACY_ASSIGNMENT : general_workflow
    VOLUNTEER ||--o{ LEGACY_ASSIGNMENT : claims
    EDGE_DEVICE ||--o{ EDGE_OBSERVATION : produces
    EDGE_SIMULATION_RUN o|--o{ EDGE_OBSERVATION : generates
    EDGE_OBSERVATION ||--o{ EDGE_MEASUREMENT : contains
    EDGE_DEVICE ||--o{ EDGE_FEATURE_SNAPSHOT : features
    EDGE_DEVICE ||--o{ EDGE_RISK_ASSESSMENT : assessments
    EDGE_RISK_EVENT ||--o{ EDGE_RISK_TRANSITION : history
    EDGE_RISK_EVENT ||--o{ EDGE_RISK_REVIEW : reviews
```

This is a conceptual relationship diagram, not executable migration DDL. Flood
place memberships also live in report JSON; not every relationship is a SQL FK.
`PHOTO_REVIEW` maps to `flood_photo_reviews`, `RESCUE_TASK` to
`flood_rescue_tasks`, and `LEGACY_ASSIGNMENT` to `assignments`.

```mermaid
flowchart LR
    Stored["Private source reports<br/>Exact coordinates, address, contact,<br/>assistance details and private photo blobs"]
    Auth["Flood access check<br/>Hashed reporter key OR hashed operational token<br/>Coordinator city scope / responder team assignment"]
    Private["Authorized response<br/>Evidence, contact, tasks, AI observations and audit"]
    Coarse["Public serializer<br/>Deterministic coarse location and restricted fields"]
    Public["Public map/list and allowed summaries<br/>No household point or sensitive assistance details"]
    Legacy["Legacy ORM query isolation<br/>Protected flood reports/incidents excluded"]
    Stored --> Auth --> Private
    Stored --> Coarse --> Public
    Stored --> Legacy

    classDef storage fill:#F3E8FF,stroke:#9333EA,color:#581C87,stroke-width:2px
    classDef guard fill:#FFE4E6,stroke:#E11D48,color:#881337,stroke-width:2px
    classDef ui fill:#DBEAFE,stroke:#2563EB,color:#172554,stroke-width:2px
    class Stored storage
    class Auth,Coarse,Legacy guard
    class Private,Public ui
```

- Originals and display derivatives are private SQLite blobs in `flood_media`.
  Derivatives are resized JPEGs without photo metadata; this does **not** redact faces.
- Flood media requires reporter ownership or scoped operational access. Public
  publication is disabled. API responses use `Cache-Control: no-store`.
- Operational identity uses provisioned opaque tokens, not a portal-wide login or
  OAuth system. Stored credentials are hashes. No portal-wide RBAC is claimed.
- SQLite uses WAL and a busy timeout. Version-checked updates prevent silent
  concurrent changes to operational incidents/tasks. Startup creates missing tables
  and runs the existing additive compatibility/flood migrations; there is no Alembic service.

### Geographic aggregation

Reports retain original and normalized addresses, string door numbers, observation
times, coordinate source/accuracy/confirmation, and location-resolution state.
Places group locality, street, landmark and building identities; door numbers are
not globally unique. Unresolved textual reports remain visible without a fabricated point.

Backend incident filters also drive summaries. Reviewed canonical situations—not
the sum of every report—provide people counts. Exact, estimated, unknown and
responder-confirmed counts remain distinct; buildings and shared teams are deduplicated.
Conflicting evidence and stale observations remain visible. Grouping suggestions
require human review. Merges preserve source reports/history and explicitly handle tasks.

Map precision is limited: point clustering and street filters/group statistics exist;
automatic zoom-level locality/street/building summary switching is incomplete. The
map currently plots the returned page while summaries can cover all filtered matches.
There are no fabricated street flood boundaries or verified rescue routes.

## 5. External data, social leads and simulated edge warnings

```mermaid
flowchart TB
    Sources["Configured source records"] --> Gate["Ingestion gate<br/>live request + environment flag + provider configuration"]
    Seed["Deterministic demo seed"] --> Normalize
    Gate -.-> Providers["Government / CAP / SACHET<br/>USGS / EONET<br/>News and search adapters"]
    Providers --> Normalize["Normalize IncidentCandidate<br/>Hazard, provenance, time and location uncertainty"]
    Normalize --> Dedup["Upsert by source and external ID"]
    Dedup --> Priority["Explainable general priority scoring"]
    Priority --> GeneralDB[("General incidents and ingestion runs")]
    GeneralDB --> Allocation["Balanced-greedy allocation<br/>Preview then explicit confirmation"]

    Search["Helpers query"] --> Login["New atproto client + login per scan"]
    Login -.-> Bsky["Bluesky post search<br/>Default 10; current code cap 50"]
    Bsky --> Intent["Disaster terms + explicit help-offer rules<br/>Exclude obvious requests and negations"]
    Intent --> Unique["Deduplicate author DID"]
    Unique --> Leads["Public-post leads in browser<br/>Human review and consent needed"]

    Sim["Deterministic virtual-device simulations"] --> Telemetry
    MQTT["Optional MQTT transport"] -.-> Telemetry
    HTTP["Telemetry HTTP endpoint"] --> Telemetry["Validate telemetry and device capability"]
    Telemetry --> Features["Past-window features and quality checks"]
    Features --> Detector["Hazard-routed flood / landslide / tsunami detectors<br/>Rules, demo classifier artifacts, rolling anomaly estimate"]
    Detector --> Event["Risk-event state and transition history<br/>Persistence and spatial/quality checks"]
    Event --> Review["Human demo review"]
    Review --> CAP["CAP 1.2 export<br/>Test / Restricted / SIMULATED ONLY"]
    Telemetry & Features & Detector & Event --> EdgeDB[("Edge tables in the same SQLite database")]

    classDef ui fill:#DBEAFE,stroke:#2563EB,color:#172554,stroke-width:2px
    classDef service fill:#DCFCE7,stroke:#16A34A,color:#14532D,stroke-width:2px
    classDef storage fill:#F3E8FF,stroke:#9333EA,color:#581C87,stroke-width:2px
    classDef external fill:#FFEDD5,stroke:#EA580C,color:#7C2D12,stroke-width:2px
    classDef guard fill:#FFE4E6,stroke:#E11D48,color:#881337,stroke-width:2px
    class Search,Leads,CAP ui
    class Normalize,Dedup,Priority,Allocation,Login,Intent,Unique,Sim,HTTP,Telemetry,Features,Detector,Event service
    class Sources,Seed,GeneralDB,EdgeDB storage
    class Providers,Bsky,MQTT external
    class Gate,Review guard
```

**Current limits and non-connections:**

- Bluesky searches are read-only. Session reuse, shared caching, incremental scans,
  and application-level request budgets were discussed but are **not implemented**.
  The diagram intentionally shows login on each scan, not an optimized future design.
- Provider errors/configuration failures are surfaced, not replaced by fake live results.
  Demo examples remain separately labelled.
- The edge system is simulated decision support, not an official early-warning network.
  The default path uses rolling forecasting. A lazy optional Chronos adapter exists;
  its availability is not proof that it runs in the default pipeline.
- There is **no implemented real emergency SMS/email/push dispatch service**.
  CAP export and in-app status are not public emergency notification delivery.
- `blip-caption-api/` and `bluesky_test.ipynb` are historical experiments.
  The portal's active image client is **OpenAI**, not BLIP. An older Hugging Face
  client/configuration also exists but is not the active instantiated image provider.
- General volunteer assignments and protected flood rescue tasks are separate
  workflows even though they share the database. No automatic cross-assignment is implied.

## 6. Local development and hosted deployment

```mermaid
flowchart LR
    subgraph Local["Local development"]
        Code["Working-tree source"] --> Vite["Vite dev server<br/>127.0.0.1:5173<br/>Frontend hot reload"]
        Code --> Py["Uvicorn / FastAPI<br/>127.0.0.1:8000"]
        Vite -->|"Configured API URL and CORS"| Py
        Py --> LocalDB[("backend/data/aapad_snehi.db")]
        Env["Ignored project/backend .env<br/>Process variables take precedence"] --> Py
    end
    subgraph Build["Source-only deployment build"]
        Git["GitHub deployment branch<br/>codex/render-free-demo"] --> Node["Node 22 stage<br/>npm ci and Vite production build"]
        Git --> Python["Python 3.11 stage<br/>Backend dependencies and application"]
        Node --> Image["Single Docker image"]
        Python --> Image
    end
    subgraph Render["Render free demo — one service / one instance"]
        HTTPS["Public HTTPS endpoint"] --> Hosted["app.hosted<br/>FastAPI API routes + built SPA assets<br/>Bind 0.0.0.0 to platform PORT"]
        Image --> Hosted
        Hosted --> Ephemeral[("Ephemeral SQLite and uploads<br/>No paid persistent disk")]
        Check["Render health probe"] -->|"GET /health"| Hosted
    end
    Code -. "Explicit source-only commit and push" .-> Git

    classDef ui fill:#DBEAFE,stroke:#2563EB,color:#172554,stroke-width:2px
    classDef service fill:#DCFCE7,stroke:#16A34A,color:#14532D,stroke-width:2px
    classDef storage fill:#F3E8FF,stroke:#9333EA,color:#581C87,stroke-width:2px
    classDef external fill:#FFEDD5,stroke:#EA580C,color:#7C2D12,stroke-width:2px
    classDef guard fill:#FFE4E6,stroke:#E11D48,color:#881337,stroke-width:2px
    class Code,Vite ui
    class Py,Node,Python,Image,Hosted,Check service
    class LocalDB storage
    class Git,HTTPS external
    class Env,Ephemeral guard
    style Local fill:#EFF6FF,stroke:#60A5FA,color:#172554
    style Build fill:#F0FDF4,stroke:#4ADE80,color:#14532D
    style Render fill:#FFF7ED,stroke:#FB923C,color:#7C2D12
```

The prepared Docker configuration disables live adapters, MQTT and SACHET polling
by default. The source allowlist excludes local databases, uploads, credentials,
notebooks and Git metadata. A Docker `VOLUME` declaration is **not** a provisioned
Render persistent disk. Free-hosted reports can disappear on restart/redeploy and
idle instances can have slow cold starts.

The deployed demo is `https://aapad-snehi.onrender.com/`. The last deployment verified
in this task history used commit `df505be`; later local unified-report/photo-review
changes were not deployed. This document describes **local source architecture**,
not a claim that the hosted site is identical or that its current runtime was rechecked.

## 7. Source map and verification coverage

All paths below are relative to `aapad-snehi/` unless stated otherwise.

| Architecture area | Main source files |
|---|---|
| Navigation and client | `web/src/App.tsx`, `routes.ts`, `components/Shell.tsx`, `lib/api.ts` |
| Citizen reporting and offline drafts | `web/src/pages/FloodReportPage.tsx`, `lib/flood.ts`, `lib/photo-location.ts`, `web/public/sw.js` |
| Operational map and detail | `web/src/pages/FloodOperationsPage.tsx`, `components/FloodMap.tsx` |
| Main API and storage | `backend/app/main.py`, `config.py`, `database.py`, `models.py` |
| Protected flood domain | `backend/app/flood/routes.py`, `service.py`, `schemas.py`, `models.py`, `auth.py`, `migration.py`, `manage.py` |
| Photo screening | `backend/app/flood/photo_review.py`, `services/image_triage.py` |
| General ingestion / allocation | `backend/app/adapters/`, `services/ingestion.py`, `services/normalizer.py`, `priority.py`, `allocation/` |
| Bluesky Helpers | `backend/app/adapters/bluesky.py`, `services/social_intent.py`, `web/src/pages/BlueskyHelpersPage.tsx` |
| Edge warnings | `backend/app/edge/`, edge models in `backend/app/models.py`, `web/src/pages/EdgeEarlyWarningPage.tsx` |
| Hosting | `Dockerfile`, `.dockerignore`, `render.yaml`, `backend/app/hosted.py` |
| Tests | `backend/tests/`, frontend `*.test.ts`, `scripts/verify-flood-browser.py` |

The preceding implementation run passed 240 backend tests, 15 frontend tests and
the frontend build. Those are historical results, not a new test run for this document.
This documentation-only change was checked against current routes, imports, models,
service logic and deployment files. It neither contacts live providers nor changes
runtime behavior or deploys the application.
