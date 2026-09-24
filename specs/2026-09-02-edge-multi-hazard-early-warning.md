# Multi-hazard edge early warning

Date: 2026-09-02
Branch: `feature/edge-multi-hazard-early-warning`

## Scope

Extend the active `aapad-snehi/` application with a deterministic, seedable
edge-device telemetry prototype for flood, landslide, and tsunami risk. The
feature must preserve source provenance, require explicit human confirmation
before a simulated warning enters the existing incident queue, and never send
real emergency notifications.

## Repository findings

- The canonical Git boundary is the outer AapadSnehi repository. The nested
  product checkout contains historical Git metadata and is intentionally not
  used for this branch.
- The web application uses React, TypeScript, Vite, and Leaflet. The API uses
  FastAPI, Pydantic, SQLAlchemy, and SQLite with latitude/longitude float
  columns.
- Existing APIs are under `/api`, serialize camelCase responses, and expose
  OpenAPI through FastAPI. There is no WebSocket/SSE layer.
- The existing operational path is a provenance-aware `Incident`, an
  explainable response-priority score, and explicit administrator assignment.
  There is no separate alert table.
- Public prototype routes do not enforce authentication or RBAC. A confirmation
  field is a safety interlock, not authorization.
- Baseline verification before edits: backend 202 tests passed; frontend 11
  tests passed; production build passed. No lint command is configured.

## Implementation decisions

- Keep HTTP and in-process ingestion available without credentials. Provide an
  optional localhost-only Mosquitto/paho MQTT path, disabled by default.
- Store registered devices, normalized observations/measurements, feature
  snapshots, hazard assessments, risk events/transitions/reviews, and simulation
  runs in additive SQLAlchemy tables.
- Route devices to separate flood, landslide, and tsunami detectors. Combine a
  transparent rule score, a lightweight versioned classifier, anomaly score,
  data quality, geographic relevance, nearby agreement, and consecutive-window
  policy.
- Treat all thresholds and model results as synthetic demo assumptions. Keep
  simulation labels outside feature and inference inputs.
- Poll a cursor-based snapshot endpoint from the frontend because the current
  application has no realtime transport.
- Export CAP 1.2 with `status=Test` and an unmistakable
  `SIMULATED / DEMO ONLY` label; do not disseminate it.
- Chronos Bolt Tiny is an optional, lazy, CPU-only forecasting experiment. The
  default application uses an offline rolling forecast fallback and never
  downloads model weights.

## Verification record

Implemented in the active product without changing the existing incident,
priority, map, volunteer or adapter contracts:

- Added edge registry, simulation run, normalized observation/measurement,
  feature snapshot, assessment, event, transition and review persistence.
- Added strict schema/registry validation, HTTP ingestion, optional paho/Mosquitto
  ingestion, 5/15/30/60 minute event-time features, device trust and three
  independently routed hazard engines.
- Added deterministic normal, hazard, failure, outage, spike, conflict and
  recovery scenarios with start/pause/resume/stop/reset controls.
- Added state-machine evidence, explicit demo review, simulated incident linkage,
  CAP `Test` export, cursor polling and the integrated React/Leaflet console.
- Added transparent synthetic logistic artifacts and an optional disabled
  Chronos residual adapter. No model or data was downloaded.
- Added architecture/data-contract/model-card documentation, demo configuration,
  optional Mosquitto compose file and a one-command PowerShell launcher.

Synthetic held-out fusion metrics from `python -m app.edge.training`:

- Flood: precision/recall/F1/ROC-AUC 1.0, Brier 0.008224.
- Landslide: precision/recall/F1/ROC-AUC 1.0, Brier 0.005676.
- Tsunami: precision 0.976744, recall 1.0, F1 0.988235, ROC-AUC 1.0,
  Brier 0.008372, 11.428571 false alarms per simulated day.

These are deliberately separable synthetic scenarios and are not evidence of
real-world performance. Chronos comparison and durable latency/degradation
benchmarks were not run.

Final verification on 2026-09-02:

- `cd aapad-snehi/backend; python -m pytest` -> 222 passed in 7.11s.
- `cd aapad-snehi/web; npm test` -> 6 files, 13 tests passed in 730ms.
- `cd aapad-snehi/web; npm run build` -> TypeScript and Vite build passed,
  1,738 modules transformed in 944ms.
- Isolated full 75-step/three-device flood probe -> completed; all devices
  reached `WARNING` near 0.67 estimated probability and one warning event was
  retained.
- Isolated Uvicorn probe -> `/health` returned `ok connected`, `/docs` returned
  HTTP 200, and OpenAPI included `/api/edge/telemetry`.
- `python -m compileall -q app`, PowerShell launcher parse, and
  `docker compose -f docker-compose.edge.yml config --quiet` -> passed.
- `python -m app.edge.evaluation` -> loaded and reported all three committed
  artifact metric groups; Chronos remained `not_run`.
- `git diff --check` -> passed (only Git line-ending notices).

There is no repository lint command. The user-authored untracked
`aapad-snehi/specs/prosed_plan_model.md` was preserved unchanged. No remote push
was performed.

## Feature file inventory

- Backend integration: `backend/app/{config,database,main,models}.py`,
  `backend/requirements.txt`, `backend/requirements-chronos.txt`.
- Edge package: `backend/app/edge/{__init__,cap,catalog,chronos,detectors,evaluation,features,future_sources,mqtt,routes,schemas,service,simulator,training}.py`,
  `data/edge_config.json`, and the three JSON files in `model_artifacts/`.
- Backend tests: `backend/tests/test_edge_early_warning.py`.
- Frontend integration: `web/src/App.tsx`, `routes.ts`, `routes.test.ts`,
  `styles.css`, `types.ts`, `components/Shell.tsx`,
  `components/EdgeRiskMap.tsx`, `lib/api.ts`, `lib/api.edge.test.ts`,
  `pages/OverviewPage.tsx`, and `pages/EdgeEarlyWarningPage.tsx`.
- Operations/configuration: `.env.edge.example`, `docker-compose.edge.yml`,
  `ops/mosquitto-demo.conf`, `scripts/start-edge-demo.ps1`.
- Documentation: `README.md`, `docs/EDGE_EARLY_WARNING.md`,
  `docs/EDGE_DATA_SCHEMA.md`, `docs/MULTI_HAZARD_MODEL_CARD.md`, and this
  workspace-level implementation record.
