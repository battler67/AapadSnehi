# Model expressivity: capacity, limitations and honest output language

The filename `expressitvity.md` follows the requested spelling. Here, expressivity
means what relationships a model can represent and what its outputs can say.
It is not evidence that a model understands disaster physics or causes outcomes.

## What the three selected models can express

| Model | Capacity | Prediction unit and output | What it cannot express directly |
|---|---|---|---|
| Random Forest regressor | Combines nonlinear decision-tree rules about flow, weather, season and catchment characteristics | One catchment/day; next-day discharge in m3/s | Water level, flood extent, casualties, safe evacuation routes or calibrated uncertainty |
| XGBoost classifier | Sequential boosted trees learn combinations associated with training-defined high flow | One catchment/day; calibrated score and validation-cutoff flag | Official flood danger, inundation probability, or a guaranteed safe condition below cutoff |
| Compact U-Net | Learns local and broader spatial patterns across 12 aligned environmental/current-fire channels | One 64x64 scene; next-day active-fire score at each cell | Ignition before existing fire, exact burned perimeter, arrival time at a house or verified pixel risk probabilities |

RF trees average learned outcomes and have limited extrapolation beyond training
conditions. XGBoost can express complex nonlinear boundaries, but no boundary makes
an unseen regime reliable. U-Net learns spatial relationships without explicitly
solving fire physics; it has no guaranteed conservation law or causal interpretation.
All three are statistical predictors, not physical simulators or causal models.

## Evidence: where they worked and where they did not

Primary seed 42, frozen selected models:

| Model | Population | Measured result | Meaning |
|---|---|---|---|
| Random Forest | 30 catchments; 52,071 held-out days | RMSE 287.95 m3/s; MAE 31.75; NSE 0.650 | Lower pooled RMSE than persistence 328.13, about 12.2% improvement; not a uniform per-river error guarantee |
| XGBoost | Same days; 1,515 high-flow positives | Recall 86.2%; precision 50.7%; F2 0.756; AP 0.777 | Caught many high-flow days, but roughly half of flagged days were false positives |
| U-Net | 1,689 test scenes; 6,727,699 valid pixels | Recall 59.3%; precision 19.2%; AP 0.254; IoU 0.170; Dice 0.291 | Useful exploratory spatial signal, but substantial misses and false-positive pixels |

XGBoost confusion counts: TN 49,288; FP 1,268; FN 209; TP 1,306. These are
catchment-days, not independent disasters. The model's no-flag output missed
209 high-flow days. Its 0.1351 score cutoff prioritises recall via validation F2.

U-Net newly active recall was 44.8% and AP 0.139. Extra Trees had overall AP 0.207
and IoU 0.173. U-Net improved AP/recall but not overall IoU. Unchanged-fire
persistence had IoU 0.183 but zero newly active recall. A single metric does not
make U-Net the universal winner. Its low precision is especially important before
any alerting use. Pixel false positives are not counts of false emergency alerts.

On 46,349 matched flood test days, RF RMSE was 290.58 versus LSTM about 609.75.
The larger selected LSTM did not win and was unstable across seeds. LSTM/TCN and
Extra Trees artifacts remain research comparators, not three additional validated
products. No landslide model was trained; label-quality problems blocked that task.

These are measured differences, NOT demonstrated statistical significance or
operational superiority. Three-seed repeats measure training randomness, not
independent-event uncertainty. See [FINAL_REPORT.md](FINAL_REPORT.md) and the raw
leaderboards for matched populations, uncertainty, seed variation and failures.

## How outputs should be expressed in the portal

| Output | Appropriate wording | Misleading wording to avoid |
|---|---|---|
| RF discharge | "Estimated next-day discharge: [value] m3/s, historical replay" | "Water rises by [value] metres" or "This area will flood" |
| XGBoost score | "Model-estimated high-flow exceedance score; not field-validated" | "Verified chance of flooding" |
| XGBoost flag | "Above research review cutoff" / "Below research review cutoff" | "Flood confirmed" / "Safe" |
| U-Net heat map | "Uncalibrated next-day active-fire model score" | "80% certainty this place will burn" |
| U-Net binary map | "Predicted active-fire cells at validation-selected cutoff" | "Exact future burned boundary" |
| Missing data | "Insufficient data; prediction unavailable" | "0% risk" |

Discharge q95 defines WHAT the classifier predicts. The score cutoff defines WHEN
the portal shows a review flag. Neither is an official flood threshold. Nominal
next-day targets must not be described as measured 24-hour warning lead time.
No confidence interval is returned by the adapters; do not invent one from RMSE.

## Geographic, temporal and input limits

- Flood training is CAMELS-IND retrospective data with selected catchments,
  train 1991-2008, validation 2009-2013 and test 2014-2018. IDs, historical
  catchment properties and past discharge matter; arbitrary rivers are unsupported.
- Earlier flood protocol errors led to reruns after test results had already been
  viewed. This is disclosed, not a pristine untouched external validation claim.
- Reanalysis/static-map publication delays prevent an operational replay claim.
  Do not substitute tomorrow's measured weather for a forecast available today.
- Catchment-average rainfall/soil moisture are not equivalent to one point sensor.
  Soil-water units and layers differ from many edge probes. A sensor-compatible
  ablation is not sensor field validation.
- Wildfire training covers the supplied US dataset, not validated Indian forests.
  Published scenes lack individual dates, coordinates and event IDs; overlapping
  locations/long fires may cross splits. Independent-fire counts are unavailable.
- Each fire cell has aligned inputs, but weather resampling does not create an
  independent fine-scale weather observation. U-Net uses neighboring cells too.
- Unreported landslides are not confirmed negatives. No susceptibility score was
  substituted for a forecasting model when the label audit failed.

## Missing inputs, model size and operational readiness

Frozen flood RF diagnostic RMSE increased to 316.80 with weather outage and 491.49
with discharge outage; targets were unchanged. Those are robustness experiments,
not permission to deploy imputed predictions. Demo adapters reject absent required
inputs. Wildfire outage checking demonstrated rejection, not full outage predictive
performance. Basic validation is not a complete out-of-distribution detector.

RF artifact is about 94.2 MB, XGBoost about 0.78 MB and U-Net checkpoint about
0.50 MB. File size is not runtime RAM: Python, libraries, activations and worker
copies also consume memory. CPU adapter timing/reload evidence is in
`reports/dl_adapter_verification.json` and `reports/model_verification.json`.
Laptop measurements do not establish edge-device speed, power use or reliability.

Recommended use now: a read-only historical demonstration with typical AND poor
examples and human interpretation. Before real-world integration: verify live
source availability/units, calibrate local thresholds, obtain fresh independent
and prospective validation, measure operational false alerts/lead time, and design
monitoring and safe failure behavior. Discharge-to-level conversion needs a valid
local rating curve; inundation mapping needs additional hydraulic information.
No model here authorizes evacuation, dam-release or automatic warning decisions.
