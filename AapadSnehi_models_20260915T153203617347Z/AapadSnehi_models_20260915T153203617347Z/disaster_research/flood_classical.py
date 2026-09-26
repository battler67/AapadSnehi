from __future__ import annotations

import json
import math
import time
import traceback
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from scipy.special import expit
from sklearn.compose import ColumnTransformer, TransformedTargetRegressor
from sklearn.impute import SimpleImputer
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

from .metrics import classification_metrics, regression_metrics
from .model_registry import classification_models, load_optional, regression_models
from .paths import ARTIFACTS, PROCESSED, REPORTS, RUNS, ensure_runtime_dirs
from .run_registry import RunRegistry

DROP = {"target_discharge", "target_high_flow", "split", "date", "year", "month", "day"}


def _features(frame: pd.DataFrame):
    columns = [c for c in frame.columns if c not in DROP]
    return frame[columns], [c for c in columns if c != "catchment_id"]


def _preprocessor(numeric: list[str], scale: bool) -> ColumnTransformer:
    numeric_steps = [("imputer", SimpleImputer(strategy="median"))]
    if scale:
        numeric_steps.append(("scale", StandardScaler()))
    return ColumnTransformer([
        ("numeric", Pipeline(numeric_steps), numeric),
        ("catchment", OneHotEncoder(handle_unknown="ignore", sparse_output=False), ["catchment_id"]),
    ], verbose_feature_names_out=False)


def _sample(frame: pd.DataFrame, cap: int, seed: int) -> pd.DataFrame:
    if len(frame) <= cap:
        return frame
    # Proportional random sample preserves the natural (not artificially balanced) prevalence.
    return frame.sample(n=cap, random_state=seed).sort_values(["date", "catchment_id"])


def _probability(model, x) -> np.ndarray:
    if hasattr(model, "predict_proba"):
        return np.asarray(model.predict_proba(x))[:, 1]
    return expit(np.asarray(model.decision_function(x), dtype=float))


def _validation_f2_threshold(y, probability) -> float:
    candidates = np.unique(np.quantile(probability, np.linspace(.50, .995, 100)))
    # Keep the predeclared candidate grid, without recomputing AP/ROC 100 times.
    y = np.asarray(y, dtype=bool)
    probability = np.asarray(probability)
    scores = []
    for t in candidates:
        predicted = probability >= t
        tp = np.count_nonzero(predicted & y)
        fp = np.count_nonzero(predicted & ~y)
        fn = np.count_nonzero(~predicted & y)
        scores.append((5 * tp / max(5 * tp + fp + 4 * fn, 1), float(t)))
    return max(scores, key=lambda pair: pair[0])[1]


def _model_scale(name: str) -> bool:
    return name in {"ridge", "elastic_net", "knn", "linear_svr", "rbf_svr", "small_mlp",
                    "logistic_regression", "gaussian_nb", "lda", "regularized_qda",
                    "linear_svm", "rbf_svm"}


def screen(task: str, seed: int = 42, only: set[str] | None = None) -> pd.DataFrame:
    ensure_runtime_dirs()
    data = pd.read_parquet(PROCESSED / "flood" / "features.parquet")
    train, validation = data[data.split == "train"], data[data.split == "validation"]
    x_validation, numeric = _features(validation)
    if task == "regression":
        models, optional_specs = regression_models(seed)
        target = "target_discharge"
    else:
        models, optional_specs = classification_models(seed)
        target = "target_high_flow"
    optional, optional_failures = load_optional(optional_specs)
    models.update(optional)
    registry = RunRegistry(REPORTS / "run_registry.csv")
    metrics_dir = RUNS / "flood" / "screening" / task
    metrics_dir.mkdir(parents=True, exist_ok=True)
    rows = []
    for name, reason in optional_failures.items():
        run_id = f"flood-screen-{task}-{name}-s{seed}"
        registry.upsert({"run_id": run_id, "disaster": "flood", "stage": "screening", "task": task,
                         "model": name, "seed": seed, "status": "failed", "reason": reason})
    for name, (estimator, cap) in models.items():
        if only and name not in only:
            continue
        run_id = f"flood-screen-{task}-{name}-s{seed}"
        metric_path = metrics_dir / f"{name}_s{seed}.json"
        prior = {r["run_id"]: r for r in registry.read()}.get(run_id)
        if prior and prior["status"] == "completed" and metric_path.exists():
            rows.append(json.loads(metric_path.read_text(encoding="utf-8")))
            continue
        sampled = _sample(train, cap, seed)
        x_train, _ = _features(sampled)
        y_train = sampled[target].to_numpy()
        pipe = Pipeline([("preprocess", _preprocessor(numeric, _model_scale(name))), ("model", estimator)])
        if task == "regression":
            model = TransformedTargetRegressor(regressor=pipe, func=np.log1p, inverse_func=np.expm1,
                                               check_inverse=False)
        else:
            model = pipe
        started = time.perf_counter()
        start_utc = registry.now()
        registry.upsert({"run_id": run_id, "disaster": "flood", "stage": "screening", "task": task,
                         "model": name, "training_scope": "full" if len(sampled) == len(train) else f"capped_{len(sampled)}",
                         "seed": seed, "status": "running", "started_at_utc": start_utc})
        try:
            model.fit(x_train, y_train)
            if task == "regression":
                prediction = np.maximum(0, model.predict(x_validation))
                result = regression_metrics(validation[target], prediction)
            else:
                probability = _probability(model, x_validation)
                threshold = _validation_f2_threshold(validation[target], probability)
                result = classification_metrics(validation[target], probability, threshold)
            duration = time.perf_counter() - started
            result.update({"run_id": run_id, "model": name, "task": task,
                           "training_rows": int(len(sampled)), "training_scope":
                           "full" if len(sampled) == len(train) else f"capped_{len(sampled)}",
                           "validation_rows": int(len(validation)), "duration_seconds": duration, "seed": seed})
            metric_path.write_text(json.dumps(result, indent=2), encoding="utf-8")
            registry.upsert({"run_id": run_id, "disaster": "flood", "stage": "screening", "task": task,
                             "model": name, "training_scope": result["training_scope"], "seed": seed,
                             "status": "completed", "started_at_utc": start_utc, "ended_at_utc": registry.now(),
                             "duration_seconds": duration, "metrics_path": metric_path})
            rows.append(result)
        except Exception as exc:
            duration = time.perf_counter() - started
            reason = f"{type(exc).__name__}: {exc}\n{traceback.format_exc(limit=2)}"
            registry.upsert({"run_id": run_id, "disaster": "flood", "stage": "screening", "task": task,
                             "model": name, "seed": seed, "status": "failed", "started_at_utc": start_utc,
                             "ended_at_utc": registry.now(), "duration_seconds": duration, "reason": reason})
    leaderboard = pd.DataFrame([json.loads(p.read_text(encoding="utf-8")) for p in metrics_dir.glob(f"*_s{seed}.json")])
    if len(leaderboard):
        sort = "rmse" if task == "regression" else "f2"
        leaderboard = leaderboard.sort_values(sort, ascending=task == "regression")
        leaderboard.to_csv(REPORTS / f"flood_{task}_screening_leaderboard.csv", index=False)
    return leaderboard


def baselines() -> dict[str, object]:
    data = pd.read_parquet(PROCESSED / "flood" / "features.parquet")
    train = data[data.split == "train"].copy()
    validation = data[data.split == "validation"].copy()
    persistence = np.maximum(0, validation["discharge"].to_numpy())
    train["doy"] = train.date.dt.dayofyear
    validation["doy"] = validation.date.dt.dayofyear
    seasonal_map = train.groupby(["catchment_id", "doy"])["target_discharge"].median()
    catchment_median = train.groupby("catchment_id")["target_discharge"].median()
    seasonal = np.array([seasonal_map.get((row.catchment_id, row.doy), catchment_median[row.catchment_id])
                         for row in validation.itertuples()])
    thresholds = pd.read_csv(PROCESSED / "flood" / "selected_catchments.csv",
                             dtype={"catchment_id": str}).set_index("catchment_id")["train_q95_m3_s"]
    event_prediction = np.array([p > thresholds[str(cid).zfill(5)]
                                 for p, cid in zip(persistence, validation.catchment_id)], dtype=float)
    result = {"persistence_regression": regression_metrics(validation.target_discharge, persistence),
              "seasonal_regression": regression_metrics(validation.target_discharge, seasonal),
              "persistence_threshold_high_flow": classification_metrics(validation.target_high_flow, event_prediction)}
    path = RUNS / "flood" / "screening" / "baselines.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(result, indent=2), encoding="utf-8")
    return result
