# Owner handoff: research models into the AapadSnehi demo

## Read this first: publication and completion state

Verified on 2026-09-15: GitHub branch `ml_experiments` points to
`7e7b96c4c07014d51aa4558134a896e49c7685e0`, the original repository commit.
The research commit failed because Git author name/email were unset. Consequently,
the new research source, results and documentation have NOT yet been pushed.
This is a dated status snapshot, not a live check of future pushes.

Weights/checkpoints are local and Git-ignored. Even after the source commit is
pushed, a clone will NOT contain them. Reports are intended for Git; model binaries,
raw/processed datasets, execution logs and replay tables are not.

Completed locally: flood and wildfire experiments, three-seed finalist evaluations,
saved preprocessing, checkpoint reload checks, historical plots and reports.
Landslide prediction is blocked by source/label quality. No model is connected to
the portal, no research API route exists, and nothing is deployed by this handoff.

Read [MODEL_USER_GUIDE.md](MODEL_USER_GUIDE.md) for exact inputs and outputs,
[expressitvity.md](expressitvity.md) for capabilities and limitations,
and [FINAL_REPORT.md](FINAL_REPORT.md) for the full scientific evidence.

## 1. What to transfer to the owner

Paths below are relative to `disaster_research/`:

| Purpose | Local artifact | Approximately |
|---|---|---:|
| Next-day discharge | `artifacts/flood/selected_regression.joblib` | 94.2 MB |
| High-flow classifier | `artifacts/flood/selected_event.joblib` | 0.78 MB |
| Next-day fire mask | `runs/wildfire/screening/dl/wildfire-screen-unet-b16-s42/best.pt` | 0.50 MB |

Random Forest has serialized trees, not neural-network weights. XGBoost's artifact
includes the model, preprocessing, validation calibrator and alert cutoff. U-Net's
checkpoint contains its neural weights/configuration/cutoff; normalization is in
`wildfire_data.py` and must be transferred with the code. Avoid the legacy
`xgboost_*` filenames: some contain another selected estimator.

Use `reports/model_handoff_manifest.json` for exact sizes, SHA-256 checksums,
versions, feature names and cutoffs. Verify hashes BEFORE deserializing any model:

```powershell
Get-FileHash disaster_research/artifacts/flood/selected_regression.joblib -Algorithm SHA256
Get-FileHash disaster_research/artifacts/flood/selected_event.joblib -Algorithm SHA256
Get-FileHash disaster_research/runs/wildfire/screening/dl/wildfire-screen-unet-b16-s42/best.pt -Algorithm SHA256
```

Compare with a manifest received through a trusted channel. Hashes establish file
identity, not model safety or scientific validity. Joblib and these PyTorch loaders
can execute code: never load an uploaded or untrusted artifact.

Transfer these three files through an owner-approved private artifact channel,
preserving relative paths. A separately approved versioned release/object store is
another option after checking distribution terms. No artifact upload is performed
here. Do not remove ignore rules or commit the entire data/runs directory.

For a demo without downloading full datasets, also transfer:

- `artifacts/handoff/`: real-input JSON requests, corresponding outputs and provenance.
- Relevant `runs/flood/replay/` CSVs and `runs/wildfire/replay/` NPZs for the existing
  typical/poor historical visualizations, if interactive replay is needed.
- The source, `reports/`, `requirements.txt` and environment version record.

Keep observations used for outcome comparison separate from prediction requests.
Inspect source licences/provenance before redistributing dataset excerpts publicly.

## 2. Prepare and verify the handoff

On the original research machine, from the repository root:

```powershell
.\.venv\Scripts\python.exe -m disaster_research.export_handoff
.\.venv\Scripts\python.exe -m pytest disaster_research/tests -q
```

The exporter uses actual held-out data, does not train, and does not upload files.
Its flood outputs are checked against saved held-out predictions, and the fire
output against `runs/wildfire/replay/unet_scene_0.npz` (also required to export).
Fire scene 0 is
selected by file order, not performance. Its dates are explicitly illustrative
adapter-test dates because original scene timestamps are unavailable.

On the owner's machine, use an isolated research environment. Consult
`reports/environment_versions.json`; the measured environment used Python 3.13,
scikit-learn 1.7.1 and PyTorch 2.14.0+cu130. `requirements.txt` does not install
PyTorch. Install a compatible trusted PyTorch build separately; CPU inference is
sufficient for this demo. Do not assume serialized estimators are portable across
arbitrary dependency versions, or replace the backend's existing environment.

After restoring the artifact paths, replay the requests using the commands in the
user guide and compare with their saved outputs (allow small floating-point
differences). Full research tests require the processed flood table; they are not
a portable inference-only test suite. Full `verify_models` also needs saved
held-out tables and wildfire TFRecords; missing these is not a model-load success.

### Important: clone versus resume

The tracked execution ledgers contain COMPLETED statuses from this machine, while
the corresponding local runs are ignored. A fresh clone must NOT blindly run the
resume drivers and interpret skipped jobs as successful reproduction.

For inference, transfer the selected artifacts; no retraining is needed. For a
fresh full experiment, preserve the published reports as evidence, create a new
local run state, acquire/audit/prepare the datasets, then run the documented drivers
with fresh ledgers. Existing drivers do not automatically distinguish a fresh clone
from a machine with all completed artifacts. Never erase the original evidence or
reuse old completed statuses as proof of a new run. New results need new provenance
and may differ by hardware/library version.

## 3. Portal integration plan (proposed, not implemented)

The current product is `aapad-snehi/`: Python FastAPI backend and a separate web
frontend. Keep research isolated. Start with a read-only historical demo that
returns saved outputs; label those as PRECOMPUTED. Inference-on-request can follow
after validating the owner environment.

Suggested future contracts, not existing endpoints:

| Proposed route | Request | Response/purpose |
|---|---|---|
| `GET /api/research-demo/catalog` | none | Allowlisted examples, models, provenance and availability |
| `POST /api/research-demo/flood` | `example_id` | RF discharge and separate XGBoost score/flag |
| `POST /api/research-demo/wildfire` | `example_id` | Current, predicted and separately loaded observed maps |

The frontend submits an example ID, not arbitrary file paths, pickle uploads or
unreviewed sensor packets. The backend owns all input loading, preprocessing,
timestamps and artifact selection. Use repository-relative configuration rather
than the original laptop's absolute paths.

Keep the heavy research dependencies in a local inference service or dedicated
environment if necessary. If models are loaded into the main backend, do it at
startup once per worker and verify memory before increasing worker count. Current
adapter functions load a model on EACH call: caching is a future integration task,
not a current capability. Limit concurrent inference, request size and runtime;
CPU-only with one worker is a reasonable starting point for a local demo.

Present one flood chart and three fire maps (current/predicted/observed). Fire
arrays have no supplied coordinates; do not invent a Leaflet location. Show
unknown pixels distinctly. Catchment data must not be relabelled as a point-sensor
measurement. Retain typical and poor cases, with their documented selection rule.

## 4. Boundary checks still needed before exposing an API

The Python adapters perform useful checks, but are NOT a complete public API:

- Validate JSON types, row limits, finite values, array dimensions, valid IDs and
  physical units; `units_confirmed=true` is only a caller assertion.
- Check individual data-source timestamps and history completeness. The classical
  adapter sees engineered rows and cannot prove that rolling features are causal.
- Keep real publication timestamps separate from assumed replay dates. U-Net
  currently returns a horizon but no authoritative target timestamp; the wrapper
  must supply truthful metadata or explicitly mark dates unavailable.
- Reject stale/missing inputs. Do not replace a failure with zero risk. Distinguish
  invalid input, unavailable artifact and internal error; do not expose tracebacks.
- Check output finiteness and expected shapes as well as input validity. Existing
  adapters are research utilities, not comprehensive out-of-distribution detectors.
- Return source, model version AND artifact checksum, data-quality status,
  `mode=historical_replay`/`precomputed`, and `operationally_validated=false`.
- Store any demo threshold override separately. Never mutate the selected artifact
  or display original precision/recall as metrics for an adjusted cutoff.
- Never write model outputs directly into official-warning or dispatch flows.
  Preserve deterministic no-credential mode. Prototype routes are public: a route
  named admin or research does not supply authentication/RBAC.

## 5. Acceptance checklist and next owner action

- [ ] Obtain the three artifacts and verify every checksum.
- [ ] Run actual-input adapter examples; compare outputs with saved reference JSON.
- [ ] Check missing weather, stale timestamps, unknown catchments and wrong shapes.
- [ ] Label wildfire scores uncalibrated, high flow non-official and all data historical.
- [ ] Show observed outcomes only after/alongside prediction, never as model inputs.
- [ ] Verify no demo action publishes warnings or dispatches volunteers.
- [ ] After implementation: backend `python -m pytest`; web `npm.cmd test` and
      `npm.cmd run build`; verify `/health`, `/docs`, and the complete browser flow.

Next code task: implement the catalog and a read-only replay page. Live sensor
integration, public deployment, authentication and operational forecasting are
separate tasks requiring additional validation and authority.

To finish the requested source push, the owner must first provide their Git author
name/email (a GitHub noreply address is fine). Configure them repository-locally,
review the staged files, commit the research and new documentation, then push
`ml_experiments`. Unrelated `test.py` must remain excluded. This document does not
claim that the blocked commit or a weight upload has succeeded.
