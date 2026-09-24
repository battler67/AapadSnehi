# Trained model portal integration

## Branch

`codex/ml-prediction-portal`

## Scope

Integrate the trusted artifacts in `AapadSnehi_models_20260915T153203617347Z`
as a read-only historical research prediction workflow in the existing FastAPI
and React/Vite portal. The feature must not publish alerts, mutate incidents, or
claim operational validation.

## Model inventory and input-to-output pipeline

| Model ID | Purpose | Artifact | Input and preprocessing | Output | Initial compatibility |
|---|---|---|---|---|---|
| `flood-random-forest-v2` | Estimate next-day catchment discharge | `selected_regression.joblib` | One complete 71-column CAMELS-IND engineered catchment-day row. The saved pipeline owns categorical and numeric preprocessing; inputs must not be normalized again. | Non-negative discharge in m3/s; no confidence interval or flood extent. | Reference sample reproduced `41.75717115160998` m3/s. |
| `flood-xgboost-event-v2` | Flag next-day flow above the catchment training-only q95 | `selected_event.joblib` | Same ordered 71-column engineered row. Saved pipeline and validation calibrator are applied, followed by cutoff `0.13507359650769765`. | Calibrated high-flow score and research review flag; not inundation probability or an official threshold. | Artifact/hash valid; local runtime initially missing `xgboost==3.0.4`. |
| `wildfire-unet-v1` | Estimate next-day active-fire scores around an existing fire | `best.pt` | Twelve aligned raw 64x64 channels in documented order. Environmental values are clipped and standardized with `wildfire_data.STATS`; `PrevFireMask` remains -1/0/1. | Uncalibrated 64x64 score map and validation cutoff `0.4495303297042897`. | Checkpoint valid. Portal adapter will avoid the research module's inference-only `tfrecord` import. |

No landslide model exists: training was blocked by source and label-quality
gates. It will be documented as unavailable rather than replaced with a proxy.

## Artifact audit

- All seven Markdown files were read as primary documentation.
- All 108 files listed in `MANIFEST.json` match their SHA-256 and byte count.
- Unlisted files are `START_HERE.md` and seven generated `__pycache__/*.pyc`
  files; bytecode and report images are not runtime inputs.
- Model loaders will verify the three allowlisted artifact hashes before trusted
  deserialization. Client-supplied paths or uploaded models are prohibited.

## Plan

1. Add an allowlisted, cached model registry with strict schemas, units, ranges,
   timestamps, payload bounds, output finiteness checks, safe errors, and model
   availability health.
2. Reuse saved joblib preprocessing for flood models and reproduce the documented
   U-Net architecture/channel normalization for the unchanged checkpoint.
3. Add versioned catalog, health, scenario, and prediction routes under
   `/api/v1/ml`.
4. Add deterministic synthetic/demo generators separate from inference. Synthetic
   flood rows retain a supported catchment's static attributes; wildfire scenarios
   generate aligned 64x64 channels with an explicit existing-fire mask.
5. Add `/ml-predictions` with dynamic model metadata, readable feature forms,
   JSON spatial input, synthetic scenarios, accessible results, and explicit
   historical/non-operational disclaimers.
6. Test hash/load caching, preprocessing, validation boundaries, saved-reference
   outputs, API contracts and errors, model/page switching, manual and synthetic
   submissions, responsive browser flow, and all existing suites.

## Safety decisions

- The API reports `unavailable` when dependencies or artifacts are missing and
  never substitutes precomputed output for a failed inference.
- Risk labels describe research review state only. A below-cutoff result is never
  labelled safe.
- U-Net scenes have no coordinates or authoritative dates, so the UI uses a grid,
  not a geographic map.
- Outputs are isolated from incident creation, public warnings, dispatch, and the
  existing simulated edge-warning pipeline.

## Verification log

- Added an allowlisted, hash-verifying model registry, cached loaders, strict
  preprocessing/validation services, synthetic-scenario adapters, and four
  `/api/v1/ml` routes. The three saved artifacts all ran successfully without
  modifying their weights.
- Added the responsive `/ml-predictions` page, navigation entry, dynamically
  generated scalar forms, 64x64 spatial JSON input, accessible result summaries,
  probability bars, a score-grid canvas, and explicit research/demo disclaimers.
- `python -m pytest`: **263 passed** in 54.43 seconds.
- `npm test`: **17 passed** across 8 files.
- `npm run build`: passed. Vite retains its existing advisory warning for the
  roughly 537 kB application bundle.
- Browser/API full-story check passed with an exact CORS origin: catalog loading,
  model switching, synthetic and manual Random Forest submissions, synthetic
  XGBoost submission, synthetic U-Net submission, mobile 390x844 layout, and a
  clean browser console. `/health` and `/docs` both returned HTTP 200.
- Saved-reference checks reproduced Random Forest output
  `41.75717115160998`, XGBoost high-flow score
  `5.828218411220035e-05`, and every U-Net output cell within `rtol=1e-5` and
  `atol=1e-6` of the exported reference output.
- Browser examples included a synthetic Random Forest estimate of 41.811 m3/s,
  a manual-input Random Forest estimate of 42.026 m3/s, XGBoost below the
  research cutoff at 0.01%, and a U-Net result with 11 cells above its saved
  validation cutoff. First-load timings include model import/hash/deserialization;
  the observed warmed Random Forest request was 162.73 ms.
- Follow-up runtime fix: the portal virtual environment had resolved the broad
  scikit-learn constraint to `1.9.0`, which could deserialize the `1.7.1`
  artifact but failed inside `SimpleImputer.transform`. Requirements now pin
  scikit-learn `1.7.1` and joblib `1.5.2`; health reports incompatible runtimes,
  and unexpected estimator compatibility errors return a sanitized HTTP 503.
  The repaired `.venv` produced an XGBoost HTTP 200 with score
  `5.6392673766250425e-05`; all targeted ML tests and the full backend suite
  completed successfully in that environment.

## 2026-09-24 hosted timeout remediation

### Problem

The deployed page exposed the browser's raw `signal timed out` exception when a
sleeping free Render service did not answer the model-catalog request within 30
seconds. The checked-out Docker allowlist also omitted the deployment-only ML
requirements and packaged artifacts required by the Dockerfile.

### Plan and scope

1. Allow the catalog and saved-model requests enough time for a free-service
   cold start, while translating aborts into a clear retryable message.
2. Add an explicit model-catalog retry without changing model inputs, outputs,
   safety labels, warning flows, or dispatch behavior.
3. Include only the already-audited hosted flood artifacts and pinned hosted ML
   requirements in the Docker build context.
4. Run focused frontend tests, full frontend tests/build, full backend tests,
   Docker build/smoke checks, secret and whitespace audits, then commit, push,
   deploy, and verify the public page and ML endpoints.

### Verification in progress

- Focused ML frontend tests: **3 passed**.
- Full frontend suite: **18 passed** across 8 files.
- Frontend production build: passed; the existing roughly 538 kB chunk-size
  advisory remains.
- Full backend suite: **272 passed** using repository-local pytest temp/cache
  paths after the default Windows temp directory denied access.
- Local Docker verification was skipped at the user's request to prioritize the
  existing Render showcase URL; Render build and runtime checks are required
  before completion.
- Render service inspection found the existing service builds from the outer
  repository root with automatic deploys disabled. Added a root-level Docker
  entrypoint and strict build-context allowlist that reuse the nested active
  product without moving or duplicating its source tree.
