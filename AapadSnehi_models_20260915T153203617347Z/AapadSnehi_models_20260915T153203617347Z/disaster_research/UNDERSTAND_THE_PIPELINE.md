# Understand the pipeline

The three questions need separate models. Flood forecasting estimates tomorrow's
observed discharge in a catchment. Landslide forecasting would estimate tomorrow's
rainfall-triggered occurrence in a geographic cell. Wildfire spread estimates
tomorrow's active-fire map around an existing fire.

## From observations to examples

`flood_data.py` pairs inputs through day t with observed discharge on day t+1.
It adds discharge lags, rainfall totals over 3, 7, 14 and 30 days, recent trends,
seasonality and static terrain/soil/geology attributes. Missing targets are removed,
never interpolated. High flow means exceeding that river's training-period 95th
percentile; it does not establish inundation or an official danger level.

Classical models learn from these calculated summaries. Boosted trees repeatedly
correct earlier errors. An LSTM learns which parts of a daily sequence to remember;
a TCN learns patterns through causal temporal filters. Both share a model across
catchments using an identity embedding. The classical static inputs differ from
the sequence inputs, so the comparison does not isolate architecture alone.

Wildfire records supply 12 aligned input maps and a target map. Classical models
learn from sampled pixels and nearby active-fire counts. A U-Net learns spatial
patterns from whole maps. Unknown targets (-1) are excluded from loss and metrics.
Newly active evaluation uses pixels known inactive at the current time. Satellite
active-fire detections are not exact burned-area boundaries.

COOLR contains event reports, not a complete daily landslide census. Missing reports
are background examples, not confirmed negatives. Dates, locations, duplicate
reports and independent storms must pass an audit before training. The current
audit has not established a valid forecasting dataset; no landslide model exists.

## Why evaluation needs care

Training teaches the model; validation selects settings and alert cutoffs; testing
measures the frozen choice. Corrected flood splits follow target dates: 1991–2008,
2009–2013 and 2014–2018. Wildfire retains the published files. Dependent days or
pixels are never randomly redistributed across splits.

Leakage means using information unavailable when making the prediction. Examples
are fitting a scaler on test data, defining high flow from the entire discharge
record, and using tomorrow's measured rain as an input. Historical reanalysis and
delayed products make these retrospective experiments. A next-day target alone
does not demonstrate a measured 24-hour warning lead time.

The first flood implementation had catchment-selection and split-boundary errors.
Its results are preserved under `superseded/flood_protocol_v1/`. Corrected results
must disclose earlier test inspection; a fresh independent evaluation is needed
before claiming untouched external validation.

Rare events make accuracy misleading: predicting no event can be highly accurate
while missing every event. Recall counts the fraction of positives found; precision
counts the fraction of alerts that are correct. F2 weights recall more strongly.
Average precision uses scikit-learn's `average_precision_score`, not trapezoidal
PR integration. Brier measures probability error, but uncalibrated margins should
not be interpreted as risk probabilities. IoU/Dice measure fire-map overlap.
MAE/RMSE measure discharge error; NSE/KGE add hydrological comparisons. Check
per-catchment results because large rivers can dominate pooled scores.

Seed variation measures training randomness, not uncertainty across independent
events. Neighboring pixels and consecutive days are correlated. Bootstrapping
them as independent samples would make uncertainty look artificially small.

## Reproduce the experiments

Run from the repository root in PowerShell. Install `requirements.txt` in an
isolated environment and a hardware-compatible PyTorch build. The measured run
uses Python 3.13 and PyTorch 2.14.0+cu130; another laptop may require CPU execution.

```powershell
.\.venv\Scripts\python.exe -m disaster_research hardware
.\.venv\Scripts\python.exe -m disaster_research acquire --dataset flood
.\.venv\Scripts\python.exe -m disaster_research acquire --dataset wildfire
.\.venv\Scripts\python.exe -m disaster_research audit-flood
.\.venv\Scripts\python.exe -m disaster_research prepare-flood
.\.venv\Scripts\python.exe -m disaster_research audit-wildfire
.\.venv\Scripts\python.exe -m disaster_research prepare-wildfire
.\.venv\Scripts\python.exe -m disaster_research screen-wildfire
.\.venv\Scripts\python.exe -m disaster_research.execute
.\.venv\Scripts\python.exe -m disaster_research.finish
.\.venv\Scripts\python.exe -m disaster_research.report
```

The sequential driver saves logs in `runs/execution_v2/`, commands and statuses in
`reports/execution_v2.json`, and skips its completed jobs. Individual model failures
remain in `reports/run_registry.csv`; process success alone does not establish model
success. Preserve downloads, checksums, preprocessing and checkpoints. Load only
trusted joblib/PyTorch artifacts.

Run the two drivers in order, never concurrently. The finishing driver includes
finalist repeats, held-out evaluation, replay and reload verification, and records
its own resumable state in `reports/finishing_execution.json`. Adapter payloads
must include timezone-aware `prediction_time`, `latest_input_available_at` and
`latest_observation_time`; these are caller-supplied claims, not proof that historical
products were actually published at those times.

## Presenting and applying results

See `FINAL_REPORT.md` for current evidence. State the prediction unit, geography and
input availability before showing scores. Compare against persistence (tomorrow
equals today). Include typical and poor cases chosen by a documented rule. A more
complex model is worthwhile only when its measured benefit justifies its cost.

These experiments do not validate edge devices. Catchment-average rainfall differs
from a point rain gauge; reanalysis moisture differs from a probe. Integration needs
aligned sensor histories, availability timestamps, local validation and drift checks.
Missing required inputs must produce insufficient data, never reassuring low risk.
