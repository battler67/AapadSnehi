from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
from tfrecord.reader import tfrecord_loader

from .paths import INTERIM, REPORTS, ensure_runtime_dirs

FEATURES = ["elevation", "pdsi", "NDVI", "pr", "sph", "th", "tmmn", "tmmx",
            "vs", "erc", "population", "PrevFireMask"]
TARGET = "FireMask"
STATS = {
    "elevation": (0., 3141., 657., 649.), "pdsi": (-6.1, 7.9, 0., 2.7),
    "NDVI": (-9821., 9996., 5158., 2467.), "pr": (0., 44.5, 1.7, 4.5),
    "sph": (0., 1., .0072, .0043), "th": (0., 360., 190.3, 72.6),
    "tmmn": (253.2, 298.9, 281.1, 9.), "tmmx": (253.2, 315.1, 295.2, 9.8),
    "vs": (0., 10., 3.9, 1.4), "erc": (0., 106., 37., 21.),
    "population": (0., 2534., 26., 155.), "PrevFireMask": (-1., 1., 0., 1.),
}


def files(split: str) -> list[Path]:
    return sorted((INTERIM / "wildfire").glob(f"next_day_wildfire_spread_{split}_*.tfrecord"))


def records(split: str):
    for path in files(split):
        for record in tfrecord_loader(str(path), None):
            yield {key: np.asarray(value, dtype=np.float32).reshape(64, 64) for key, value in record.items()}


def normalized_inputs(record: dict[str, np.ndarray]) -> np.ndarray:
    channels = []
    for name in FEATURES:
        value = record[name].astype(np.float32, copy=True)
        if name != "PrevFireMask":
            low, high, mean, std = STATS[name]
            value = np.clip(value, low, high)
            value = (value - mean) / std
            value[~np.isfinite(value)] = 0
        channels.append(value)
    return np.stack(channels)


def audit() -> dict[str, object]:
    ensure_runtime_dirs()
    split_stats = {}
    global_min = {key: np.inf for key in (*FEATURES, TARGET)}
    global_max = {key: -np.inf for key in (*FEATURES, TARGET)}
    nonfinite = {key: 0 for key in (*FEATURES, TARGET)}
    for split in ("train", "eval", "test"):
        scenes = valid = positive = unknown = current_positive = newly_positive = 0
        all_unknown_scenes = no_known_current_fire_scenes = 0
        file_counts = {path.name: 0 for path in files(split)}
        for path in files(split):
            for raw in tfrecord_loader(str(path), None):
                scenes += 1
                file_counts[path.name] += 1
                shaped = {key: np.asarray(value).reshape(64, 64) for key, value in raw.items()}
                target, previous = shaped[TARGET], shaped["PrevFireMask"]
                known = target >= 0
                all_unknown_scenes += int(not known.any())
                no_known_current_fire_scenes += int(not (previous==1).any())
                valid += int(known.sum())
                positive += int((target == 1).sum())
                unknown += int((target < 0).sum())
                current_positive += int((previous == 1).sum())
                newly_positive += int(((target == 1) & (previous == 0)).sum())
                for key, value in shaped.items():
                    finite = np.isfinite(value)
                    nonfinite[key] += int((~finite).sum())
                    if finite.any():
                        global_min[key] = min(global_min[key], float(value[finite].min()))
                        global_max[key] = max(global_max[key], float(value[finite].max()))
        split_stats[split] = {"files": len(files(split)), "file_scene_counts": file_counts,
                              "all_unknown_target_scenes":all_unknown_scenes,
                              "no_known_current_fire_scenes":no_known_current_fire_scenes,
                              "scenes": scenes, "valid_target_pixels": valid,
                              "positive_target_pixels": positive,
                              "target_prevalence": positive / valid if valid else None,
                              "unknown_target_pixels": unknown, "current_positive_pixels": current_positive,
                              "newly_active_pixels": newly_positive}
    report = {
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "dataset": "Next Day Wildfire Spread, Kaggle version 2",
        "geographic_unit": "64 x 64 scene on approximately 1 km CONUS grid; pixel is evaluation unit within scene",
        "issue_time": "dataset day t after current active-fire/environmental inputs are assembled",
        "input_observation_interval": "current-day aligned channels; PrevFireMask is current fire state",
        "input_availability": "retrospective; archive lacks per-channel publication timestamps needed for operational replay",
        "forecast_horizon": "next supplied day", "target_interval": "next-day satellite active-fire mask",
        "label_provenance_uncertainty": "MODIS active-fire detections; -1 target pixels are unknown and masked. Active fire is not an exact burned-area perimeter.",
        "intended_use": "predict spread of an existing fire, not ignition before a fire starts; research comparison only",
        "features": FEATURES, "units_and_train_statistics": STATS,
        "observed_min": global_min, "observed_max": global_max, "nonfinite_values": nonfinite,
        "splits": split_stats,
        "split_audit": "Published train/eval/test files preserved. Paper describes random whole-week 8:1:1 allocation during 2012-2020, with a one-day buffer between weeks. This is not an unseen-region or independent-fire split: long fires and recurring geography may cross splits. TFRecords expose no dates, coordinates or event IDs for stronger event grouping. Scene counts are not independent fire counts.",
        "augmentation_policy": "No augmentation in the initial screen; any future augmentation must remain within source split.",
    }
    (REPORTS / "wildfire_dataset_audit.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    return report
