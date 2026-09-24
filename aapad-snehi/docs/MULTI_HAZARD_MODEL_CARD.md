# Multi-hazard model card

## Intended use

This is a **multi-hazard edge-data simulation, anomaly detection and early-risk-estimation prototype**. It demonstrates architecture and explainability using synthetic observations. It does not establish real-world disaster prediction accuracy and must not drive public alerts.

## Architecture and choices

The registry’s installed purposes route each device only to compatible independent engines. Flood uses water level/rise, rainfall, flow and saturation; landslide uses moisture, pore pressure, tilt, vibration and rain; tsunami uses bottom pressure residual, sea-level anomaly/rate, waves and optional seismic evidence.

Each engine combines:

1. transparent bounded rules (`<hazard>-rules-v1`);
2. a logistic classifier (`<hazard>-demo-v1`) saved as auditable JSON containing preprocessing means/scales, ordered features, coefficients, intercept, configuration hash, split sizes and metrics;
3. a lightweight rolling forecast residual anomaly;
4. data quality, device trust, nearby agreement and configured geographic relevance.

Features are event-time windows of 5, 15, 30 and 60 minutes: current/mean/min/max/std, slope, rate, acceleration, EWMA, accumulation, recent-baseline deviation, cross-sensor couplings, consecutive threshold exceedance, missing percentage, health and nearby agreement. Queries and tests enforce `observation.timestamp <= as_of`.

The classifier training command is:

```powershell
cd backend
python -m app.edge.training --seed 20260902
python -m app.edge.evaluation
```

Scenario groups—not adjacent windows—are split 70/15/15. All training data is synthetic. The committed artifacts report the following held-out synthetic results; unusually strong values reflect the deliberately separable generator and **must not be generalized**.

| Hazard | Approach | Precision | Recall | F1 | ROC-AUC | Brier |
|---|---|---:|---:|---:|---:|---:|
| Flood | Rules | 1.000 | 0.944444 | 0.971429 | 1.000 | 0.018206 |
| Flood | Classifier | 0.972973 | 1.000 | 0.986301 | 1.000 | 0.005079 |
| Flood | Fusion | 1.000 | 1.000 | 1.000 | 1.000 | 0.008224 |
| Landslide | Rules | 1.000 | 0.933333 | 0.965517 | 1.000 | 0.014550 |
| Landslide | Classifier | 1.000 | 1.000 | 1.000 | 1.000 | 0.001907 |
| Landslide | Fusion | 1.000 | 1.000 | 1.000 | 1.000 | 0.005676 |
| Tsunami | Rules | 1.000 | 1.000 | 1.000 | 1.000 | 0.022546 |
| Tsunami | Classifier | 0.976744 | 1.000 | 0.988235 | 1.000 | 0.002924 |
| Tsunami | Fusion | 0.976744 | 1.000 | 0.988235 | 1.000 | 0.008372 |

Fusion false alarms per simulated day are flood 0.0, landslide 0.0 and tsunami 11.428571. Missed-event rate is 0.0 for all three. Mean detection lead time is flood 0.0, landslide 0.0 and tsunami 0.142857 simulated minutes. Ingestion-to-risk latency, invalid/duplicate rejection percentage, and degraded-network performance are exercised by tests but not yet benchmarked into a durable evaluation report; they are accurately marked “not measured” for this phase.

## Chronos experiment

`amazon/chronos-bolt-tiny` is an optional, disabled-by-default zero-shot forecaster, not a hazard classifier. `ChronosBoltAdapter` lazily loads on CPU, refuses network downloads unless `AAPAD_EDGE_CHRONOS_ALLOW_DOWNLOAD=true`, forecasts selected channels and converts forecast residuals to anomaly features. The app runs with the built-in rolling fallback and without PyTorch, Chronos, internet access or a Hugging Face token. Chronos comparison metrics are `not_run` because no model was downloaded during this implementation. References: [Chronos forecasting](https://github.com/amazon-science/chronos-forecasting), [Chronos Bolt Tiny](https://huggingface.co/amazon/chronos-bolt-tiny).

## Limitations and ethics

- Synthetic thresholds, calibration and geographic priors are demo assumptions, not validated warning standards.
- Nearby agreement is distance-based; it does not yet model watershed, terrain or propagation direction.
- Logistic outputs can be overconfident outside the synthetic distribution.
- Ground truth never enters inference, but the current generator and training generator remain conceptually related.
- CAP status is `Test`; incidents are `unverified` and prominently simulated. There is no notification integration.
