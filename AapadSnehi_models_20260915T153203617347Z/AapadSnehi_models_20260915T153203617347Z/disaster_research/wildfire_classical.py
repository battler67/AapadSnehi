from __future__ import annotations

import json
import time
import traceback

import numpy as np
import pandas as pd
from scipy.ndimage import convolve
from scipy.special import expit
from sklearn.impute import SimpleImputer
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from .metrics import wildfire_metrics
from .model_registry import classification_models, load_optional
from .paths import PROCESSED, REPORTS, RUNS, ensure_runtime_dirs
from .run_registry import RunRegistry
from .wildfire_data import FEATURES, records

PIXEL_FEATURES = [*FEATURES, "active_neighbors_3", "active_neighbors_5"]


def scene_table(record: dict[str, np.ndarray]) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    previous = record["PrevFireMask"]
    active = (previous == 1).astype(np.float32)
    n3 = convolve(active, np.ones((3, 3), dtype=np.float32), mode="constant") - active
    n5 = convolve(active, np.ones((5, 5), dtype=np.float32), mode="constant") - active
    x = np.stack([record[name] for name in FEATURES] + [n3, n5], axis=-1).reshape(-1, len(PIXEL_FEATURES))
    y = record["FireMask"].reshape(-1)
    current = previous.reshape(-1)
    valid = y >= 0
    return x[valid], (y[valid] == 1).astype(np.int8), current[valid]


def prepare_screen_samples(seed: int = 42, train_per_scene: int = 16,
                           validation_cap: int = 300_000) -> dict[str, object]:
    ensure_runtime_dirs()
    out = PROCESSED / "wildfire"
    out.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(seed)
    train_chunks = []
    train_labels = []
    for record in records("train"):
        x, y, _ = scene_table(record)
        positives, background = np.flatnonzero(y == 1), np.flatnonzero(y == 0)
        half = train_per_scene // 2
        chosen_pos = rng.choice(positives, min(half, len(positives)), replace=False) if len(positives) else np.array([], dtype=int)
        remainder = train_per_scene - len(chosen_pos)
        chosen_bg = rng.choice(background, min(remainder, len(background)), replace=False)
        chosen = np.concatenate([chosen_pos, chosen_bg])
        train_chunks.append(x[chosen]); train_labels.append(y[chosen])
    train_x, train_y = np.concatenate(train_chunks), np.concatenate(train_labels)
    # Vectorized, unbalanced sample with near-equal representation from every scene.
    validation_chunks, validation_labels, validation_current_chunks = [], [], []
    per_scene = max(1, validation_cap // 1877)
    seen = 0
    for record in records("eval"):
        x, y, current = scene_table(record); seen += len(y)
        indices = rng.choice(len(y), min(per_scene, len(y)), replace=False)
        validation_chunks.append(x[indices]); validation_labels.append(y[indices])
        validation_current_chunks.append(current[indices])
    reservoir_x = np.concatenate(validation_chunks)[:validation_cap]
    reservoir_y = np.concatenate(validation_labels)[:validation_cap]
    reservoir_current = np.concatenate(validation_current_chunks)[:validation_cap]
    filled = len(reservoir_y)
    np.savez_compressed(out / "classical_screen_samples.npz", train_x=train_x, train_y=train_y,
                        validation_x=reservoir_x[:filled], validation_y=reservoir_y[:filled],
                        validation_current=reservoir_current[:filled])
    manifest = {"seed": seed, "features": PIXEL_FEATURES, "train_rows": len(train_y),
                "train_scenes": 14979, "train_positive_fraction": float(train_y.mean()),
                "training_sampling": f"up to {train_per_scene//2} fire and remaining background pixels per scene",
                "validation_rows": filled, "validation_source_pixels_seen": seen,
                "validation_positive_fraction": float(reservoir_y[:filled].mean()),
                "validation_sampling": f"{per_scene} uniformly sampled valid pixels per published eval scene; natural within-scene prevalence, not 50/50"}
    (REPORTS / "wildfire_classical_sample_manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return manifest


def _threshold(y, p):
    from .flood_classical import _validation_f2_threshold
    return _validation_f2_threshold(y, p)


def _probability(model, x):
    if hasattr(model, "predict_proba"):
        return model.predict_proba(x)[:, 1]
    return expit(model.decision_function(x))


def screen(seed: int = 42, only: set[str] | None = None) -> pd.DataFrame:
    sample_path = PROCESSED / "wildfire" / "classical_screen_samples.npz"
    if not sample_path.exists():
        prepare_screen_samples(seed)
    sample = np.load(sample_path)
    train_x, train_y = sample["train_x"], sample["train_y"]
    val_x, val_y, val_current = sample["validation_x"], sample["validation_y"], sample["validation_current"]
    models, specs = classification_models(seed)
    optional, failures = load_optional(specs); models.update(optional)
    registry = RunRegistry(REPORTS / "run_registry.csv")
    result_dir = RUNS / "wildfire" / "screening" / "classification"; result_dir.mkdir(parents=True, exist_ok=True)
    rows = []
    for name, reason in failures.items():
        registry.upsert({"run_id": f"wildfire-screen-{name}-s{seed}", "disaster": "wildfire",
                         "stage": "screening", "task": "pixel_mask", "model": name, "seed": seed,
                         "status": "failed", "reason": reason})
    scaled = {"logistic_regression", "gaussian_nb", "lda", "regularized_qda", "knn", "linear_svm", "rbf_svm", "small_mlp"}
    for name, (estimator, cap) in models.items():
        if only and name not in only: continue
        run_id = f"wildfire-screen-{name}-s{seed}"; path = result_dir / f"{name}_s{seed}.json"
        prior = {r["run_id"]: r for r in registry.read()}.get(run_id)
        if prior and prior["status"] == "completed" and path.exists():
            rows.append(json.loads(path.read_text(encoding="utf-8"))); continue
        n = min(cap, len(train_y)); rng = np.random.default_rng(seed)
        indices = rng.choice(len(train_y), n, replace=False) if n < len(train_y) else np.arange(n)
        steps = [("imputer", SimpleImputer(strategy="median"))]
        if name in scaled: steps.append(("scale", StandardScaler()))
        steps.append(("model", estimator)); model = Pipeline(steps)
        start = time.perf_counter(); start_utc = registry.now()
        scope = "full_sample" if n == len(train_y) else f"capped_{n}"
        registry.upsert({"run_id": run_id, "disaster": "wildfire", "stage": "screening", "task": "pixel_mask",
                         "model": name, "training_scope": scope, "seed": seed, "status": "running", "started_at_utc": start_utc})
        try:
            model.fit(train_x[indices], train_y[indices])
            probability = _probability(model, val_x); threshold = _threshold(val_y, probability)
            result = wildfire_metrics(val_y, probability, val_current, threshold)
            duration = time.perf_counter() - start
            result.update({"run_id": run_id, "model": name, "training_rows": n,
                           "training_scope": scope, "validation_rows": len(val_y),
                           "duration_seconds": duration, "seed": seed,
                           "calibration_note": "screen probabilities are uncalibrated; threshold selected on validation F2"})
            path.write_text(json.dumps(result, indent=2), encoding="utf-8")
            registry.upsert({"run_id": run_id, "disaster": "wildfire", "stage": "screening", "task": "pixel_mask",
                             "model": name, "training_scope": scope, "seed": seed, "status": "completed",
                             "started_at_utc": start_utc, "ended_at_utc": registry.now(),
                             "duration_seconds": duration, "metrics_path": path})
            rows.append(result)
        except Exception as exc:
            registry.upsert({"run_id": run_id, "disaster": "wildfire", "stage": "screening", "task": "pixel_mask",
                             "model": name, "training_scope": scope, "seed": seed, "status": "failed",
                             "started_at_utc": start_utc, "ended_at_utc": registry.now(),
                             "duration_seconds": time.perf_counter()-start,
                             "reason": f"{type(exc).__name__}: {exc}\n{traceback.format_exc(limit=2)}"})
    board = pd.DataFrame(rows)
    if len(board):
        board = board.sort_values("f2", ascending=False)
        board.to_csv(REPORTS / "wildfire_classical_screening_leaderboard.csv", index=False)
    return board


def persistence_baseline(split: str = "eval") -> dict[str, object]:
    ys, ps, currents, scene_rows = [], [], [], []
    for scene_id, record in enumerate(records(split)):
        _, y, current = scene_table(record); probability = (current == 1).astype(np.float32)
        metrics = wildfire_metrics(y, probability, current)
        scene_rows.append({"scene": scene_id, "iou": metrics["iou"], "dice": metrics["dice"],
                           "recall": metrics["recall"], "precision": metrics["precision"]})
        ys.append(y); ps.append(probability); currents.append(current)
    result = wildfire_metrics(np.concatenate(ys), np.concatenate(ps), np.concatenate(currents))
    pd.DataFrame(scene_rows).to_csv(REPORTS / f"wildfire_persistence_{split}_per_scene.csv", index=False)
    path = RUNS / "wildfire" / "screening" / f"persistence_{split}.json"; path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(result, indent=2), encoding="utf-8")
    return result
