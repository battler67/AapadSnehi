# Multi-Hazard Edge Early Warning Prototype

  ## Summary and repository findings

  - Implement on a new outer-repository branch, feature/edge-multi-hazard-early-warning, and record scope,
    decisions, edits, and verification in specs/2026-09-02-edge-multi-hazard-early-warning.md. Do not push.

  - The canonical outer repository is clean on main at 7e7b96c, tracking origin/main. The active product is
    aapad-snehi/.

  - The nested historical Git checkout is on feature/bluesky-response-intelligence and reports 47 differences—
    33 modified, 4 deleted, and 10 untracked—because it predates the flattened outer snapshot. Do not branch,
    clean, or commit through that nested repository.

  - Frontend: React 19, TypeScript, Vite, Leaflet/leaflet.heat, custom path routing, deterministic frontend
    fallback data, and IndexedDB support for citizen-report queuing.

  - Backend: FastAPI, Pydantic, SQLAlchemy, SQLite, startup create_all plus small additive SQLite compatibility
    migrations.

  - Geospatial data currently uses indexed latitude/longitude floats and application-side distance
    calculations. PostGIS is documented future architecture, not currently installed.

  - APIs use /api/..., Pydantic request models, explicit dictionary serializers with camelCase responses,
    dependency-injected SQLAlchemy sessions, and FastAPI-generated OpenAPI.

  - There is no alert model. Existing response flow is Source → Incident → explainable priority → admin review
    → explicit volunteer assignment.

  - There is no WebSocket/SSE infrastructure. Use bounded cursor-based polling behind a transport abstraction.
  - There is no authentication or enforced RBAC. Users, Volunteers, and Admin are public prototype routes; the
    new review gate must not be presented as authorization.

  - Baseline verification completed without tracked changes: backend 202 passed, frontend 11 passed, and npm
    run build passed. No lint command is configured.

  ## Backend and data pipeline

  - Add an app.edge subsystem while keeping app.main as the route assembly point:
    simulator → internal/HTTP/MQTT adapter → validator → observations → rolling features → hazard router →
    detectors → fusion → state machine → risk event → reviewed Incident.

  - Add new SQLAlchemy tables, created additively without altering existing records:
      - edge_devices: stable device ID/type, installed purpose, capabilities with canonical units, region,
        fixed location/elevation, expected interval, status, last-seen/sequence, health and trust.

      - edge_observations: unique message ID and (device, sequence) pair, event/receive timestamps, source
        protocol, health, validation/quality flags, raw normalized envelope, and isolated simulation metadata.

      - edge_measurements: one canonical observed property/value/unit per observation.
      - edge_feature_snapshots and edge_risk_assessments: as-of time, pipeline/model versions, features, rule/
        classifier/fused probabilities, confidence, contributors and quality.

      - edge_risk_events and transitions/reviews: state history, evidence snapshots, reasons, contributing
        devices, optional promoted incident ID, acknowledgements and simulation flag.

      - edge_simulation_runs: scenario configuration and process state; reset starts a new retained run rather
        than deleting evidence.

  - Model the SensorThings concepts Thing, Sensor, ObservedProperty, Location, Datastream and Observation
    internally without claiming full protocol conformance. Document the mapping against the OGC SensorThings
    standard.

  - Define schema 1.0 with camelCase aliases matching the requested envelope. Units are fixed by the versioned
    observed-property registry and repeated in device capabilities, preventing arbitrary unit submissions.

  - Validation policy:
      - Reject unsupported schema versions, unknown/unregistered devices, device-type/location mismatches,
        unsupported capabilities, non-finite or configured impossible values, naïve timestamps, readings over
        five minutes in the future, readings over 24 hours old, duplicate message IDs, duplicate device
        sequences, and empty measurement sets.

      - Accept sequence gaps and unique out-of-order readings with explicit quality flags and penalties. The
        device high-water sequence never moves backward.

      - Recompute the latest feature snapshot at the greatest stored event time using only observations whose
        timestamps are at or before that time; late readings can improve current features but cannot create
        retroactive transitions.

      - Persist scenarioId and groundTruthState only as evaluation metadata. Feature and detector interfaces
        receive no simulation object.

  - Add three explicit profiles—river_gauge, hillslope_station, and coastal_buoy—plus configurable multi-
    capability devices. Property ranges, canonical units, demo thresholds, geographic relevance and sensor
    relationships live in versioned JSON configuration and are labelled “demo assumption.”

  - Add HTTP ingestion as the always-available path. Add optional paho-mqtt support on topic aapad/edge/v1/
    {deviceId}/telemetry with topic/payload device matching and QoS 1.

  - Add an optional Mosquitto Compose file bound to 127.0.0.1:1883; MQTT remains disabled by default. The
    normal demo requires neither Docker nor credentials.

  ## Simulation, features and risk estimation

  - Implement deterministic generation for all requested scenarios: normal, gradual/flash flood, rainfall/
    slope-only landslide, tsunami-like anomaly with seismic corroboration, sensor failure, outage/recovery,
    false spike, conflicting sensors and event recovery.

  - Generate smooth trends, periodic variation, correlated channels, Gaussian noise, device bias, missing
    fields, duplicates, out-of-order delivery, latency, battery/signal decay and temporary buffering. Buffered
    packets retain original event time.

  - Supply configurable Assam river, Uttarakhand hills, Odisha coast and Visakhapatnam mixed-region templates.
    Defaults are nine devices, seed 20260902, one simulated minute per reading and 30× speed, yielding a two-
    to-four-minute judge scenario.

  - Provide API and CLI controls for scenario, device count, seed, region, speed, start, pause, resume, stop
    and reset. The backend-controlled simulator uses the same ingestion service; the CLI can publish through
    HTTP or MQTT.

  - Build 5/15/30/60-minute event-time windows with current/mean/min/max/std, linear slope, rate, acceleration,
    EWMA, rainfall accumulation, prior-baseline deviation, hazard-specific cross-sensor features, consecutive
    exceedances, missing percentage, health score and nearby anomaly count.

  - Route only capability-compatible evidence:
      - River/rain/flow sensors feed flood detection.
      - Rain/soil/pore-pressure/tilt/vibration sensors feed landslide detection.
      - Bottom-pressure/sea-level/wave/seismic evidence feeds tsunami detection.

  - Implement separate transparent rule engines and separate scikit-learn logistic-regression classifiers.
    Logistic regression is selected for inspectable per-reading contributions and compact JSON serialization.

  - Add deterministic training/evaluation commands using generated scenario instances. Split by scenario-run
    group into train/validation/test partitions so adjacent windows from one run never cross partitions.

  - Commit a small JSON artifact per hazard containing imputation/scaling values, feature order, coefficients,
    intercept, thresholds, model version, configuration hash and honestly measured metrics. Missing or corrupt
    artifacts fall back to rules and expose modelStatus: "fallback".

  - Evaluate rules, classifier and fused output separately per hazard for precision, recall, F1, ROC-AUC where
    valid, Brier score, false alarms per simulated day, missed-event rate, lead time, latency, rejection rate
    and degraded-network performance.

  - Add a disabled-by-default Chronos adapter and separate optional dependency file. It lazily loads amazon/
    chronos-bolt-tiny on CPU only when explicitly enabled and locally available; network download requires a
    second explicit flag. The model is a roughly 9M-parameter Apache-2.0 zero-shot forecaster, not a disaster
    classifier. Its residuals become optional anomaly features, while a rolling linear/EWMA residual detector
    is always available offline. Chronos repository, model card.

  - Record Chronos comparison as “not run” unless the optional experiment is actually executed; never infer
    benefit from absence or synthetic-only results.

  ## Fusion, event policy and existing workflow

  - Fuse available classifier, rule and anomaly scores using configurable default weights 0.45/0.40/0.15,
    renormalizing when a component is unavailable. Apply data-quality attenuation, explicit device/region
    relevance and a bounded nearby-agreement adjustment.

  - Keep probability, confidence and risk state separate. Confidence reflects completeness, freshness, health,
    model availability and sensor agreement; low-quality data cannot increase confidence.

  - Use demo-configured hysteresis:
      - WATCH: probability ≥0.35 for two consecutive windows.
      - WARNING: probability ≥0.60 for three windows, or two nearby devices agree for two windows.
      - CRITICAL: probability ≥0.82 for three windows with multi-device agreement.
      - Explicit immediate escalation is limited to configured extreme combinations, such as a coastal pressure
        anomaly plus corroborating simulated seismic evidence.

      - Exit CRITICAL below 0.72, WARNING below 0.50 and WATCH below 0.25 for three windows; resolved warnings
        enter RECOVERY before NORMAL.

  - A single spike never opens a warning. Missing/stale data marks devices offline and lowers confidence
    without being interpreted as low hazard.

  - Create a risk event at WATCH and retain immutable evidence for every transition: observation IDs, feature
    snapshot, model/rule/config versions, contributors, confidence, devices, timestamps and reason.

  - Review actions are acknowledge, promote_to_incident, and dismiss. Promotion requires confirmDemoOnly: true
    and a reviewer name, but this is explicitly a human-confirmation safeguard—not authentication.

  - Promotion creates an existing Incident with:
      - title prefixed SIMULATED / DEMO ONLY;
      - source_kind="simulation" and verification_status="unverified";
      - affected estimate zero, conservative existing hazard needs, and a description stating that this is
        estimated synthetic-sensor risk rather than an official warning.

  - No notification, public dissemination or volunteer dispatch occurs automatically. The resulting incident
    deep-links to /admin?incident={id} for the existing explicit assignment flow.

  - Export CAP 1.2 XML from retained risk evidence using status=Test, restricted demo scope, prominent
    simulation notes, event/urgency/severity/certainty, effective/expiry times, instructions and configured
    area geometry. CAP Test messages are explicitly non-actionable under the CAP 1.2 specification. Validate
    exports offline against a pinned CAP 1.2 schema fixture.

  ## Public API and frontend

  - Add these /api/edge capabilities:
      - POST/GET /devices and GET /devices/{deviceId}.
      - POST /telemetry.
      - GET /observations/latest and GET /devices/{deviceId}/history.
      - GET /risks with bounds/hazard/state filters and GET /risk-events/{eventId}.
      - GET /risk-events/{eventId}/cap.
      - POST /risk-events/{eventId}/reviews.
      - GET /scenarios, POST /simulations, GET /simulations/{runId}, and action endpoints for pause/resume/
        stop/reset.

      - GET /snapshot?since=<cursor>&bounds=... as the efficient UI polling aggregate.

  - Return each assessment with the requested hazard, probability, risk level, confidence, model version, top
    contributors and data quality, plus rule score, classifier status, agreement and simulated flag.

  - Add /edge-early-warning to the existing navigation and extend the current dashboard/map instead of creating
    a standalone app:
      - Device markers and risk overlays on the existing risk map, with filters for hazard, type, health and
        state.

      - Dedicated controls, native SVG sensor charts, current hazard probabilities, event timeline, battery/
        signal/last-seen, quality, nearby agreement and “Why this risk?” contributors.

      - WATCH/WARNING/CRITICAL cards, review/promotion actions, CAP download and incident deep-link.
      - A persistent SIMULATED / DEMO ONLY banner and estimated-risk wording everywhere.

  - Poll the cursor snapshot every two seconds only while the page is visible, back off on failure, and expose
    the polling implementation behind a future realtime transport interface.

  - Preserve deterministic frontend fallback data, explicitly labelled simulated. Do not add a charting
    framework or replace Leaflet.

  - Document future corroboration interfaces without implementing live integrations: IMD/CWC/NOAA observations
    and warnings, and separate satellite workers for Prithvi, Landslide4Sense and DeepSlide. Satellite products
    remain later corroboration sources, not edge models. IMD API, NOAA DART, Prithvi flood segmentation,
    Landslide4Sense, DeepSlide.

  ## Documentation, verification and acceptance

  - Create aapad-snehi/docs/EDGE_EARLY_WARNING.md, EDGE_DATA_SCHEMA.md, and MULTI_HAZARD_MODEL_CARD.md;
    update .env.example, README and generated OpenAPI descriptions.

  - Include a Mermaid architecture diagram, schema/unit catalogue, API examples, scenario catalogue, demo
    thresholds, model/evaluation provenance, limitations, real ESP32/Raspberry Pi HTTP/MQTT publisher examples
    and implemented/simulated/optional/future labels.

  - Add a one-command Windows launcher, run after dependencies are installed:
    python scripts/run_edge_demo.py --scenario gradual-river-flood --speed 30
    It starts the API/web processes, waits for health, starts the selected scenario through HTTP/internal
    ingestion, and cleans up child processes on Ctrl+C without downloading models.

  - Add backend tests for schema/range/unit/capability validation, duplicates, gaps/out-of-order packets,
    rolling statistics, strict no-future-data leakage, hazard routing, model load/fallback, scenario-group
    splitting, fusion, nearby agreement, false spikes, hysteresis/recovery, evidence retention, CAP schema
    validation, confirmation boundaries and every scenario smoke path.

  - Add a full backend acceptance test from deterministic simulator generation through ingestion, storage,
    features, risk transition and promoted simulated incident.

  - Add frontend Vitest coverage for routes, polling/cursor behavior, map filtering, sensor chart
    transformation, explanation rendering, mandatory demo badges, scenario controls and the reviewed-event
    incident link.

  - Permission-boundary tests must verify explicit confirmation and review-state rules while also preserving
    the OpenAPI regression proving that these routes do not falsely claim authentication/RBAC.

  - Run and report exact results for:
      - python -m app.edge.training
      - python -m app.edge.evaluation
      - python -m pytest
      - npm test
      - npm run typecheck
      - npm run build
      - HTTP simulator smoke, optional local MQTT smoke, /health, /docs, git diff --check, and a credential/
        forbidden-path scan.

  - No lint command currently exists; report that explicitly rather than introducing an unrelated linting
    migration.

  - Completion reporting must separate actual synthetic evaluation results by hazard and method, state whether
    Chronos was run, list changed files and commands, and describe the feature only as a simulated edge-data
  ## Assumptions and deferred work

  - Core-pipeline scope excludes scenario replay UI, durable edge store-and-forward, advanced long-term drift/
    stuck-sensor trust modelling, a full digital-twin workspace, and live official/satellite workers.

  - Basic packet-quality, health, missing-data and agreement scoring remains mandatory because it is required
    for safe fusion.

  - SQLite remains the MVP database with float coordinates; PostgreSQL/PostGIS migration is deferred.
  - The Mosquitto path is optional, local-only and disabled by default.
  - Chronos is optional, lazy, CPU-compatible and offline by default.
  - Synthetic labels and metrics establish functionality only; they do not demonstrate real-world disaster-
    prediction accuracy or validated public-warning thresholds.