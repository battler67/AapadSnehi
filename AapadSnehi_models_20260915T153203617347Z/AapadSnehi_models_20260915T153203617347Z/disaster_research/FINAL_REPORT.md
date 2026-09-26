# AapadSnehi disaster research report

Generated 2026-09-08T17:54:09.719540+00:00

Status: supported flood and wildfire experiments executed; landslide forecasting blocked by the label-quality gate. Remaining limitations are listed below. No model is field-validated or connected to warning delivery.

## Protocol and data

Hardware was inspected before training: Windows 11, Intel Core i7-13620H, 16 logical threads, approximately 23.64 GiB RAM, NVIDIA RTX 5050 Laptop GPU with 8151 MiB memory. CUDA was detected and tested. Initial workspace free space was approximately 90 GiB. Exact measurements are in reports/hardware.json. Training uses one model at a time, eight CPU threads for ensembles, float32 and zero duplicate data-loader workers. Sampled process RSS peaks are in reports/sampled_memory_peaks.json; sampling may miss short peaks and does not include every GPU allocation.

### Flood

CAMELS-IND requested record 14005378 had restricted files. Its official version 2.2, record 14999580, supplied the open archive (CC BY 4.0). The actual archive has 242 observed-flow columns, despite the 228-catchment wording in the documentation. Only observed discharge supplies targets; model-generated streamflow is excluded. The local data-description PDF confirms discharge in m³/s, precipitation in mm/day, temperature in °C, relative humidity in percent and IMDAA layer soil moisture in kg/m².

Unit: catchment-day. Inputs cover day t and preceding history; target is day t+1. Issue time is conceptually after day t closes, not a verified operational timestamp. Daily archive boundaries and product publication delays prevent a measured 24-hour lead-time claim. Training target dates are 1991–2008, validation 2009–2013, test 2014–2018. Earlier observations can supply causal history across boundaries. Missing targets are never imputed. The high-flow label uses each catchment's training-only 95th percentile, not an official flood or inundation threshold.

Retained static categories are topography, soil and geology, treated as retrospective maps of slowly changing properties. They were often published after the historical prediction dates, so this is not an operational replay. Land cover, anthropogenic attributes, full-record hydrological signatures and climate summaries are excluded. Catchment coverage eligibility uses availability in every split; ranking uses training coverage and ID, never later flow magnitudes.

Protocol correction: original runs used validation/test event counts in catchment selection, input-date split boundaries and unaudited land-cover snapshots. Some screens used random internal estimator validation. Their outputs are preserved under superseded/flood_protocol_v1 and are unsuitable as final evidence. Corrected reruns follow a fixed audit correction; previously viewed test data cannot become untouched again. Independent external validation remains necessary.

### Landslide

The current NASA endpoint attempted during acquisition returned 404. The acquired audit file is a third-party historical mirror of COOLR report-based GLC/LRC records, not a verified complete current NASA release. It contains 1,693 Indian reports, including 1,463 rainfall-triggered reports. Missing time-of-day alone does not invalidate a daily experiment. The unresolved gate is source/day accuracy, coordinate uncertainty, duplicates, reporting coverage and independent storm attribution. Proxy space/time bins are not independent storms. No landslide model or susceptibility substitute has been trained.

Required before training: obtain a verifiable COOLR export with occurrence-date uncertainty and source provenance; review duplicate/event clusters; choose a bounded region with multiple independent storms in each temporal split; resolve local-date to UTC conventions; exclude inadequately located/timed records; then acquire matching IMERG, ERA5-Land and SRTM subsets. CDS access requires an account, dataset licence acceptance and a local API configuration. Earthdata access may be required for the selected NASA granule distribution; downloads were not attempted before the label gate, so this is not evidence that every public distribution is authentication-blocked. Do not send credentials in chat.

A proposed 0.1-degree grid only supports records with suitable coordinate precision; many inventory records are much coarser and must be excluded or evaluated at a coarser scale. Background cell-days are not confirmed negatives. Operational precision/prevalence is unknown. LHASA is a nowcasting methods reference, never a source of ground-truth hazard labels.

### Wildfire

The author's Kaggle v2 archive downloaded anonymously and passed ZIP integrity checks. The supplied split contains 14,979 training, 1,877 validation and 1,689 test scenes. Test maps contain 6,727,699 valid target pixels and 84,331 active pixels (about 1.253%). These are scenes/pixels, not verified independent fires. All 12 provided input channels are retained. Unknown targets are masked. Newly active metrics exclude unknown current-fire pixels.

The paper describes whole-week random 8:1:1 splitting over 2012–2020 with a one-day buffer. The files lack event IDs, dates and coordinates, preventing stronger event/spatial grouping or timestamped replay. Long fires and recurring locations may cross splits. Inputs describe day t and the label day t+1; satellite/derived-product delays are unavailable. This is retrospective existing-fire spread prediction. Resampled weather at 1 km is not an independent 1 km observation.

Classical screening samples at most 16 training pixels per scene, with up to eight positives: 239,001 total rows before model-specific caps. Validation screening uses 296,878 uniformly sampled pixels across all validation scenes without balancing. Calibration on validation addresses training oversampling but cannot establish field calibration. Final model evaluation must use every valid pixel in the same held-out maps for ML and DL. The DL input normalization follows published training-only constants; classical screening uses raw inputs and train-fit preprocessing, a preprocessing difference that must be acknowledged.


## Results and recommendations

Flood classical choices from validation: **random_forest discharge regressor** and **xgboost high-flow classifier**. Finalist training uses all 197,250 training rows. Seed 42 is the primary artifact; no best seed is selected.

| Seed | Test rows | Discharge RMSE (m³/s) | MAE (m³/s) | NSE | Event F2 | Event recall | Event precision | Event AP |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| 42 | 52071 | 287.9507 | 31.7549 | 0.6499 | 0.7563 | 0.8620 | 0.5074 | 0.7768 |
| 43 | 52071 | 290.4624 | 31.9411 | 0.6438 | 0.7543 | 0.8601 | 0.5056 | 0.7793 |
| 44 | 52071 | 287.0045 | 31.7732 | 0.6522 | 0.7567 | 0.8607 | 0.5102 | 0.7755 |

Seed-42 event accuracy 0.9716, prevalence 0.0291, Brier 0.0121; confusion matrix [TN, FP, FN, TP] = [49288, 1268, 209, 1306]. False-positive denominator is all negative catchment-days. These are high-flow days, not independently verified disasters.

Selected flood DL run: `flood-screen-dl-lstm-l90-s42-h128`. Reload prediction equality: True. Its full eligible test population has 46349 sequences; sequence gaps mean it differs from the classical population.

Recommended flood research model: **random_forest** for discharge, selected by validation RMSE; retain the compact LSTM as the main DL comparison artifact. The separate high-flow classifier is selected independently. None supplies official danger levels.

Direct comparison below uses exactly **46349 shared held-out catchment-days**. Inputs differ: classical engineered/static features versus DL daily dynamic sequences and identity. Training windows and sample counts differ; this is not a controlled architecture-only ablation.

| Model | Matched RMSE (m³/s) | Matched MAE | NSE | High-flow RMSE | Macro catchment NSE |
|---|---:|---:|---:|---:|---:|
| random_forest | 290.5844 | 30.9034 | 0.6562 | 1567.0286 | 0.6383 |
| lstm | 609.7488 | 46.1107 | -0.5139 | 2376.6183 | 0.3280 |
| persistence | 335.1275 | 35.7134 | 0.5427 | 1624.9951 | 0.4816 |

Alert episodes: {"observed_episodes": 484, "missed_episodes": 90, "alert_episodes": 759, "false_alert_episodes": 424, "criterion": "Any same-target-day overlap counts; this measures episode detection, not pre-onset lead time"}

Catchment bootstrap intervals and peak-day errors are in `flood_matched_analysis.json` and `flood_peak_errors.csv`. Nested/shared-storm catchments violate strict independence; these are descriptive uncertainty estimates, not guaranteed confidence coverage.

Sensor-compatible ablation RMSE: 293.8519 m³/s. Frozen rich-model missing-input stress: weather_outage RMSE 316.7973, discharge_outage RMSE 491.4918. Targets were unchanged. These degraded-input predictions are diagnostic only; inference adapters reject missing required inputs.

| Regression-derived high-flow prediction (matched days) | Precision | Recall | F2 | AP of discharge exceedance score |
|---|---:|---:|---:|---:|
| random_forest | 0.7675 | 0.6959 | 0.7092 | 0.7779 |
| lstm | 0.7070 | 0.6411 | 0.6533 | 0.7029 |

Discharge exceedance scores rank forecasts relative to training q95; they are not calibrated probabilities. Their Brier score is intentionally undefined.

On matched test days DL did not reduce discharge RMSE relative to the selected classical model. Read this alongside validation selection and the disclosed prior test inspection; it does not establish operational superiority.

The largest LSTM errors include abrupt source-observed discharge changes at catchment 04062 in December 2017–January 2018. For the 2018-01-14 target, the preceding observation is about 19,258 m³/s and the next-day target about 189 m³/s, while the LSTM predicts about 55,578 m³/s. These observations remain in all applicable evaluations. The transition merits gauge/source review; the experiment cannot establish whether it represents a real change or a data-quality problem. The larger network's log-discharge extrapolation amplifies the error. See flood_matched_hydrographs.png and the exported worst-error window.

Separate fixed-config unseen-catchment extension: 6 held catchments, 10420 test days, RF RMSE 278.0848 versus persistence 302.5930. Historical local discharge was allowed; no held-out high-flow thresholds were estimated. See `flood_unseen_results.json`.

Recommended wildfire research model: **compact U-Net**, based on validation warning F2 after each method's declared selection procedure. U-Net validation F2 0.3729; classical validation F2 0.3516. Classical validation is sampled whereas DL validation uses full maps, so the final full-map test comparison below is essential. This recommendation concerns existing-fire spread, not ignition or Indian field conditions.

### Wildfire full-map comparison

Both methods use the same complete published test maps; unknown targets are masked. Classical training is capped/sampled; U-Net training uses full maps. Final metrics below are not calculated on a balanced test sample.

| Model (seed 42) | Valid pixels | IoU | Dice | Precision | Recall | F2 | AP | Newly active recall | Newly active AP |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| extra_trees | 6727699 | 0.1734 | 0.2956 | 0.2001 | 0.5653 | 0.4141 | 0.2073 | 0.4056 | 0.0955 |
| compact U-Net | 6727699 | 0.1700 | 0.2906 | 0.1925 | 0.5933 | 0.4188 | 0.2539 | 0.4480 | 0.1388 |
| persistence | 6727699 | 0.1830 | 0.3093 | 0.3572 | 0.2728 | 0.2863 | 0.1065 | 0.0000 | 0.0092 |

The U-Net recommendation prioritises recall-weighted warning performance: it improves AP and newly active recall over Extra Trees, but does not improve IoU/Dice. Persistence has the highest IoU here while missing every newly active pixel. Thus DL is not an across-the-board winner; the low precision also precludes automatic public alerts.


U-Net scores are uncalibrated weighted-loss outputs. Classical probabilities are validation-calibrated. Neither is validated as field risk. Seed variation is in `wildfire_dl_seed_results.json` and `wildfire_classical_final_results.json`; scene uncertainty is in `wildfire_replay_and_uncertainty.json` and does not establish independent-fire uncertainty.

### Full screening records

All 15 flood regressors, 18 flood classifiers and 18 wildfire classifiers were executed. Separate validation leaderboards are under reports/. Columns identify capped training scope; do not equate those screens with full-data finalist results. LSTM sequence lengths 30/60/90 and a causal TCN were screened; a 128-unit LSTM challenger and two U-Net loss weights were budgeted. Raw run statuses and failures remain in run_registry.csv, execution_failure_history.json and the execution logs.

## Resources, artifacts and verification

The original wildfire persistence and U-Net validation-summary attempts failed on all-unknown scenes. Empty scenes now have undefined metrics and contribute no valid pixels. U-Net resumed from its saved checkpoint; its first failed invocation spent 406.7 seconds, which must be added to resumed invocation time when reporting total work. No failed execution is represented as successful training from scratch.

Flood classical artifact sizes: {'regression': 94244417, 'classifier': 777938} bytes; measured 256-row regression inference 0.0215 seconds. Times in raw finalist rows include fit and evaluation, not pure training only.

Flood DL checkpoint: 375715 bytes. Three-seed training variation is recorded separately from basin uncertainty.

Wildfire classical artifact: 234258580 bytes; 256-pixel inference 0.0868 seconds.

U-Net checkpoint: 499337 bytes; reload equality True.

CPU adapter verification used real held-out inputs and eight threads. Both DL adapters reproduced reloaded-model outputs and rejected missing rainfall. Warm median forward latency (ten repeats): flood_lstm: 0.46 ms; wildfire_unet: 1.88 ms. Model loading/preprocessing timings are separately recorded in dl_adapter_verification.json. These are laptop timings, not edge-device measurements. Wildfire adapter-test timestamps are illustrative because the source scenes lack timestamps. Wildfire missing-input testing checks safe rejection, not imputed-outage predictive performance.

Saved finishing-stage maximum sampled process RSS: 2.78 GiB. Device-wide peak GPU use: 4264 MiB, including unrelated processes. Earlier monitor coverage is incomplete, so these are not guaranteed whole-experiment maxima.

Exact hardware and dependency versions, acquisition checksums and feature definitions are in reports/. Sampled RSS peaks are lower bounds sampled every five seconds; they do not include all GPU allocations. The initial monitored flood fits used roughly 1–3 GB process RAM, below the working-memory target; consult the saved per-command measurements for exact values.

Saved selected classical artifacts are in artifacts/flood/selected_regression.joblib, selected_event.joblib and artifacts/wildfire/selected_pixel.joblib. DL checkpoints and curves remain in their recorded run directories. Research adapters accept engineered rows, daily flood sequences or supplied-style fire maps with schema/unit/time checks. They return insufficient_data for missing required inputs. No application endpoint or warning delivery was connected.

Research tests: eight passed. Backend: 202 passed after repairing existing Pillow. Web: 11 tests and production build passed. Local API /health and /docs returned 200 with live adapters disabled; verification server stopped. Model-specific reload checks are in model_verification.json, dl_adapter_verification.json and final DL results.

## Limits and unfinished work

Landslide next-day prediction remains blocked; no model or risk timeline is claimed. Required label and access steps are described above. All recommendations are research choices: flood prior test inspection, retrospective static maps/reanalysis, daily availability uncertainty, non-independent catchments/fire scenes and unknown field prevalence limit generalisation. Edge-device field validation, operational weather forecasts, true release-time replay, local warning thresholds and prospective external validation remain necessary. A reduced feature experiment cannot replace sensor calibration or a river rating curve.

Plots/replays include typical and poor cases selected by median/worst error, rather than only favorable examples. A complete independent event count is unavailable for wildfire and landslide. The selected 30 flood catchments span five CWC basin prefixes and may be nested. Expansion beyond this cohort was deferred while completing comparisons and three-seed checks.

## Reproduce and resume

```powershell
.\.venv\Scripts\python.exe -m disaster_research.execute
.\.venv\Scripts\python.exe -m disaster_research.finish
.\.venv\Scripts\python.exe -m disaster_research.report
```

Run one driver at a time. The first driver must exit before the second starts. Each skips its completed jobs; raw logs and exact commands are in reports/execution_v2.json and reports/finishing_execution.json. See UNDERSTAND_THE_PIPELINE.md for acquisition and feature-building commands. Only trusted checkpoints should be loaded.

## Sources


[CAMELS-IND requested release](https://zenodo.org/records/14005378), [used v2.2 release](https://zenodo.org/records/14999580), [dataset paper](https://essd.copernicus.org/articles/17/461/2025/).

[COOLR](https://gpm.nasa.gov/applications/landslides/coolr), [IMERG](https://gpm.nasa.gov/data/imerg), [ERA5-Land](https://cds.climate.copernicus.eu/datasets/reanalysis-era5-land), [SRTM](https://www.earthdata.nasa.gov/data/instruments/srtm), [LHASA code](https://github.com/nasa/lhasa), [LHASA methods](https://www.frontiersin.org/journals/earth-science/articles/10.3389/feart.2021.640043/full).

[Author wildfire dataset](https://www.kaggle.com/datasets/fantineh/next-day-wildfire-spread), [official code](https://github.com/google-research/google-research/tree/master/simulation_research/next_day_wildfire_spread), [paper](https://arxiv.org/abs/2112.02447).
