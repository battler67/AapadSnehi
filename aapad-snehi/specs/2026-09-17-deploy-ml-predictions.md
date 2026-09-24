# Deploy ML predictions page

## Branch

`codex/deploy-ml-predictions`

## Problem

The frontend `/ml-predictions` route is present in the deployed bundle, but
`GET /api/v1/ml/models` returns HTTP 500. The Docker build installs only base
dependencies and neither copies model metadata/artifacts nor configures a model
root inside the container.

## Scope and plan

1. Package the allowlisted Random Forest and XGBoost flood artifacts, their
   exact manifest, and the deterministic scenario seed inside the backend.
2. Install the artifact-compatible hosted inference dependencies and configure
   the container model root.
3. Make catalog metadata failure a truthful unavailable state instead of a 500.
4. Test checksums, catalog health, real saved-model inference, frontend build,
   and the deployed browser/API flow.

The free Render demo intentionally omits the PyTorch wildfire runtime/checkpoint
to control image and memory cost. The card remains visible as unavailable. No
live data adapters, warnings, or automated decisions are introduced.

## Major edits

- Added a deployment-only flood inference dependency set.
- Added the trusted hosted artifact bundle under `backend/model_artifacts/`.
- Updated the Docker image to copy and use the bundle.
- Hardened model catalog generation for missing metadata.
- Added packaged-bundle regression coverage and deployment documentation.

## Verification

- Focused ML tests: 13 passed.
- Full backend suite: 272 passed.
- Frontend suite: 17 passed across 8 files.
- Frontend production build: passed; existing 500 kB chunk-size warning remains.
- Hosted-bundle API smoke: catalog 200, XGBoost high scenario prediction 200,
  ML health 200/ready; both flood artifacts verified and the omitted wildfire
  checkpoint reported `artifact_missing`.
- Render deploy `dep-dam2gmfcgkoc7383mjb0` succeeded from merge commit
  `d3c73ab` in 1m52s; `/health` returned 200 during rollout.
- Live browser catalog: Random Forest and XGBoost ready; U-Net truthfully
  disabled as `dependency_missing`.
- Live XGBoost high synthetic scenario: prediction succeeded with high-flow
  score `0.5208` and review flag set; cold inference was about 12 seconds and
  the cached repeat about 8.5 ms.
- Live Random Forest low synthetic scenario: prediction succeeded with
  estimated next-day discharge `41.811 m3/s`; cold inference was about 1.66 s.
