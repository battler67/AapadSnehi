# Trained disaster-model integration

## Purpose and safety boundary

The `/ml-predictions` page runs three trusted, already-trained artifacts from the
local `AapadSnehi_models_20260915T153203617347Z` handoff. It is a historical
research demonstration. It does not create incidents, issue alerts, dispatch a
team, or consume live sensors, weather, satellite, or official-disaster feeds.

The backend owns an allowlisted registry and verifies each artifact SHA-256 before
deserialization. Clients cannot provide model paths or upload model files. Missing
artifacts or dependencies produce an explicit unavailable response; saved outputs
are never substituted for failed inference.

## Integrated model inventory

| Model | Purpose | Weight file | Input shape/features | Preprocessing | Output | Status |
| ----- | ------- | ----------- | -------------------- | ------------- | ------ | ------ |
| Random Forest | Next-day catchment discharge | `artifacts/flood/selected_regression.joblib` | One ordered 71-feature CAMELS-IND catchment-day row | Saved joblib pipeline; no second normalization | Non-negative discharge estimate in m³/s | Integrated and reference-verified |
| XGBoost | Next-day catchment training-q95 exceedance | `artifacts/flood/selected_event.joblib` | Same 71-feature engineered row | Saved pipeline, then saved validation calibrator and cutoff `0.13507359650769765` | Calibrated high-flow score and research review flag | Integrated and reference-verified |
| Compact U-Net | Next-day activity around an existing wildfire | `runs/wildfire/screening/dl/wildfire-screen-unet-b16-s42/best.pt` | Twelve aligned raw `64×64` channels | Documented channel order; clip/standardize with `wildfire_data.STATS`; leave `PrevFireMask` as -1/0/1 | Uncalibrated `64×64` score grid and cutoff `0.4495303297042897` | Integrated and reference-verified |
| Landslide | Proposed rainfall-triggered occurrence | None | No validated schema/artifact | Not applicable | Not available | Skipped: source and label quality failed the research gate |

All 108 files listed in the handoff `MANIFEST.json` matched their recorded hashes.
Seven `__pycache__` files and `START_HERE.md` are unlisted; bytecode and report
images are not inference inputs. Report images remain scientific context, but the
page derives no prediction or explainability value from them.

## Input and preprocessing

### Flood models

The complete ordered schema is returned by `GET /api/v1/ml/models`. It includes
22 dynamic/engineered fields, string `catchment_id`, and historical static
topography/soil/geology values. `catchment_id` must retain leading zeros and be one
of the 30 trained catchments. Current-flow/rainfall/weather units and documented
ranges come from `MODEL_USER_GUIDE.md` and
`reports/feature_units_and_availability.json`. Static attributes have no complete
validated manual range in the handoff; the UI says to use exact catchment values.

The API orders the row using the artifact's `feature_columns`. It rejects missing,
extra, Boolean, non-finite, extreme, and unseen-catchment values. Documented-range
departures produce warnings. The serialized estimator owns categorical encoding,
scaling, calibration, and model inference.

### Wildfire U-Net

The required keys are `elevation`, `pdsi`, `NDVI`, `pr`, `sph`, `th`, `tmmn`,
`tmmx`, `vs`, `erc`, `population`, and `PrevFireMask`. Every grid must be finite
and exactly `64×64`; `PrevFireMask` accepts only -1, 0, and 1 and must contain at
least one active cell. `FireMask` is never accepted as input.

The portal adapter reproduces the documented compact U-Net architecture and
normalization directly. This avoids the research module's inference-time import
of the training-only `tfrecord` reader. The checkpoint is unchanged. Values
outside training clip ranges are clipped with an explicit warning. Scores are
uncalibrated and are not displayed as probability.

## API

### `GET /api/v1/ml/models`

Returns descriptions, versions, availability, readable feature schemas, units,
documented ranges, scenarios, outputs, and limitations. It also reports that
landslide is unavailable and lists future source adapter names.

### `GET /api/v1/ml/health`

Returns per-model dependency/artifact/checksum status and IDs currently loaded in
the process cache. `verified_not_loaded` is a healthy lazy state.

### `GET /api/v1/ml/models/{model_id}/scenarios/{scenario_id}`

Generates deterministic `low`, `medium`, or `high` synthetic inputs separately
from inference. Flood scenarios retain real static attributes for supported
catchment `03005` and alter labelled synthetic dynamics. Wildfire scenarios create
aligned grids with an existing-fire mask. They have no ground truth.

### `POST /api/v1/ml/predict`

```json
{
  "modelId": "flood-random-forest-v2",
  "source": "manual",
  "features": { "row": { "complete": "71-feature row" } },
  "unitsConfirmed": true
}
```

Only `manual` and `synthetic` are connected. Reserved `weather_api`, `iot_sensor`,
`edge_device`, and `official_disaster_api` sources return a truthful not-connected
error. Optional timezone-aware prediction, availability, and observation times are
accepted. The default payload limit is 3 MB (`AAPAD_ML_MAX_PAYLOAD_BYTES`). The
response includes the model/version, outcome, research review state, available
scores, input summary, warnings, limitations, validation flag, and inference time.

## Frontend workflow

1. Select a model and review its target, required features, availability, and limitations.
2. Load a labelled synthetic scenario or switch to manual editing.
3. Flood models render grouped readable fields; U-Net accepts documented spatial JSON.
4. Submit and review the real saved-model output. The fire chart is non-geographic.
5. Warnings, limitations, input summary, timing, and disclaimers remain visible.

## Local setup

The handoff is auto-discovered as a sibling of `aapad-snehi/`. To use a different
trusted location, set `AAPAD_ML_MODEL_ROOT`. Never use an upload directory.

```powershell
cd aapad-snehi\backend
python -m pip install -r requirements.txt
python -m pip install -r requirements-ml.txt
python -m uvicorn app.main:app --reload

cd ..\web
npm install
npm run dev
```

The flood artifacts require scikit-learn `1.7.1` because that is the version
used to fit and serialize their preprocessing pipelines. Do not widen this pin
without exporting and verifying fresh artifacts. In particular, scikit-learn
`1.9.0` can deserialize the current pipeline but fails at inference because its
`SimpleImputer` runtime state is incompatible. `GET /api/v1/ml/health` reports
that mismatch instead of presenting the model as ready.

PyTorch packages are platform-specific and large. The main deployment dependency
file intentionally stays light; install `requirements-ml.txt` only on a service
with enough storage/RAM. Otherwise catalog health truthfully reports unavailable
models. The 94 MB forest loads once per worker, so account for worker duplication.

### Hosted Render demo

The Docker image sets `AAPAD_ML_MODEL_ROOT=/app/model-artifacts` and includes a
minimal, checksum-verified bundle for the Random Forest and XGBoost flood models.
`backend/requirements-ml-deploy.txt` pins their inference dependencies. The free
demo does not install PyTorch or ship the U-Net checkpoint, so the wildfire card
is deliberately unavailable there instead of returning a fabricated prediction.
Use the full local `requirements-ml.txt` and sibling handoff folder to test all
three models.

## Verification

```powershell
cd aapad-snehi\backend
python -m pytest tests\test_ml_inference.py
python -m pytest

cd ..\web
npm test
npm run build
```

Tests compare all three outputs with exported real reference JSON. Expected RF is
`41.75717115160998 m³/s`; XGBoost is `0.00005828218411220035`; U-Net compares all
4096 cells with `rtol=1e-5, atol=1e-6`.

### Recorded saved-artifact smoke test

| Model | Exact sample | Validated / transformed shape | Raw saved-model output | Portal interpretation |
|---|---|---|---|---|
| `flood-random-forest-v2` | First row of `artifacts/handoff/random_forest_input.json` | `(1, 71)` named input frame to `(1, 100)` after the saved preprocessor | `41.75717115160998` after the saved target inverse-transform | Next-day discharge estimate of `41.757 m³/s`; confidence and operational risk are not assessed. |
| `flood-xgboost-event-v2` | First row of `artifacts/handoff/xgboost_input.json` | `(1, 71)` named input frame to `(1, 100)` after the saved preprocessor | Calibrated high-flow score `5.828218411220035e-05` | Below saved review cutoff `0.13507359650769765`; this never means safe. |
| `wildfire-unet-v1` | All channels in `artifacts/handoff/unet_input.json` | Twelve `(64, 64)` grids to tensor `(1, 12, 64, 64)` | Score tensor `(1, 1, 64, 64)`; exported map min `0.0009755804785527289`, max `0.4258846342563629`, mean `0.012665833949611738` | Zero reference cells at or above cutoff `0.4495303297042897`; the complete 4096-cell map matches the export within tolerance. |

The timed API response reports inference time for the integration path. It does
not include frontend rendering and varies significantly on the first request as
libraries, checksums, and model objects are loaded and cached.

## Known limitations

- No model is field-validated or suitable for automated public warning.
- Flood forcings/static maps are retrospective and publication times are absent.
- The classifier target is training-period q95, not verified inundation.
- U-Net data is US-based, lacks dates/coordinates/event IDs, predicts spread only
  around an existing fire, and had low held-out precision.
- First inference includes checksum/import/load latency; later calls reuse cache.
- Restart every backend worker after changing ML dependency versions; an existing
  Python process keeps the previously imported scikit-learn implementation.
- The public prototype has no authentication/RBAC. Do not expose sensitive or
  operational source data through these routes.

## Connecting real data later

Add a source adapter that creates the same validated `features` contract, then:

1. authenticate and authorize the source route;
2. verify units, identity, publication time, freshness, completeness, and provenance;
3. construct exact 30-day flood features or twelve aligned fire grids without future data;
4. retain source, artifact checksum, model version, warnings, and validation state;
5. validate prospectively on the target geography and recalibrate thresholds;
6. keep human confirmation between predictions and any alert or response action.

Do not connect point probes directly to catchment-average inputs, substitute
forecasts without retraining/validation, or map fire grids without georeferencing.
