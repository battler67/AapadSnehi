from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import brier_score_loss, f1_score, precision_score, recall_score, roc_auc_score
from sklearn.model_selection import GroupShuffleSplit
from sklearn.preprocessing import StandardScaler

from .catalog import CONFIG_PATH, edge_config
from .detectors import MODEL_DIR, rule_score


FEATURES = {
    "flood": [
        "waterLevelM_current", "waterLevelM_15m_slope", "rainfall_accumulation_60m",
        "soilMoisturePct_current", "flowVelocityMps_current", "flood_coupling",
    ],
    "landslide": [
        "soilMoisturePct_current", "poreWaterPressureKpa_current",
        "poreWaterPressureKpa_15m_slope", "tilt_vector_deg",
        "vibrationRmsMmS_current", "rainfall_accumulation_60m",
    ],
    "tsunami": [
        "seaLevelAnomalyM_current", "seaLevelRateMPerMin_current",
        "bottomPressureKpa_baseline_deviation", "waveHeightM_current",
        "earthquakeMagnitude_current", "tsunami_coupling",
    ],
}

NORMAL = {
    "flood": [2.3, 0.001, 6, 48, 1.2, 0.004],
    "landslide": [48, 30, 0.03, 0.05, 1.2, 6],
    "tsunami": [0.02, 0.002, 0.12, 0.8, 0.0, 0.02],
}

EVENT = {
    "flood": [7.2, 0.13, 115, 93, 5.8, 0.7],
    "landslide": [94, 185, 3.2, 2.8, 34, 98],
    "tsunami": [1.4, 0.22, 18, 7.5, 7.6, 1.8],
}


def generate_windows(hazard: str, seed: int, groups_count: int = 90):
    rng = np.random.default_rng(seed)
    rows: list[list[float]] = []
    labels: list[int] = []
    groups: list[str] = []
    windows: list[int] = []
    normal = np.asarray(NORMAL[hazard], dtype=float)
    event = np.asarray(EVENT[hazard], dtype=float)
    span = np.maximum(np.abs(event - normal), 0.1)
    for group_index in range(groups_count):
        positive = group_index % 2 == 1
        bias = rng.normal(0, span * 0.035)
        group_id = f"{hazard}-scenario-{group_index:03d}"
        for window in range(12):
            progress = 0.0 if not positive else max(0.0, min(1.0, (window - 2) / 7))
            center = normal + (event - normal) * progress + bias
            noise = rng.normal(0, span * 0.055)
            rows.append((center + noise).tolist())
            labels.append(1 if positive and window >= 6 else 0)
            groups.append(group_id)
            windows.append(window)
    return np.asarray(rows), np.asarray(labels), np.asarray(groups), np.asarray(windows)


def _metrics(labels: np.ndarray, probabilities: np.ndarray) -> dict[str, float]:
    predicted = probabilities >= 0.5
    return {
        "precision": round(float(precision_score(labels, predicted, zero_division=0)), 6),
        "recall": round(float(recall_score(labels, predicted, zero_division=0)), 6),
        "f1": round(float(f1_score(labels, predicted, zero_division=0)), 6),
        "rocAuc": round(float(roc_auc_score(labels, probabilities)), 6),
        "brierScore": round(float(brier_score_loss(labels, probabilities)), 6),
    }


def train_hazard(hazard: str, seed: int) -> dict:
    matrix, labels, groups, windows = generate_windows(hazard, seed)
    first_split = GroupShuffleSplit(n_splits=1, train_size=0.70, random_state=seed)
    train_idx, remaining_idx = next(first_split.split(matrix, labels, groups))
    second_split = GroupShuffleSplit(n_splits=1, train_size=0.50, random_state=seed + 1)
    validation_relative, test_relative = next(
        second_split.split(matrix[remaining_idx], labels[remaining_idx], groups[remaining_idx])
    )
    validation_idx = remaining_idx[validation_relative]
    test_idx = remaining_idx[test_relative]

    scaler = StandardScaler().fit(matrix[train_idx])
    classifier = LogisticRegression(max_iter=1000, class_weight="balanced", random_state=seed)
    classifier.fit(scaler.transform(matrix[train_idx]), labels[train_idx])
    classifier_probabilities = classifier.predict_proba(scaler.transform(matrix[test_idx]))[:, 1]
    feature_names = FEATURES[hazard]
    rule_probabilities = np.asarray(
        [rule_score(hazard, dict(zip(feature_names, row, strict=True)))[0] for row in matrix[test_idx]]
    )
    fused_probabilities = 0.53 * classifier_probabilities + 0.47 * rule_probabilities

    predicted = fused_probabilities >= 0.5
    negative_windows = labels[test_idx] == 0
    false_positives = int(np.logical_and(predicted, negative_windows).sum())
    negative_days = max(1 / 1440, int(negative_windows.sum()) / 1440)
    positive_groups = sorted(set(groups[test_idx][labels[test_idx] == 1]))
    missed = 0
    lead_times: list[float] = []
    for group in positive_groups:
        mask = groups[test_idx] == group
        group_predictions = predicted[mask]
        group_windows = windows[test_idx][mask]
        detected = group_windows[group_predictions]
        if len(detected) == 0:
            missed += 1
        else:
            lead_times.append(max(0.0, 6 - float(min(detected))))

    return {
        "hazard": hazard,
        "modelVersion": f"{hazard}-demo-v1",
        "artifactFormat": "transparent-logistic-json-v1",
        "featureOrder": feature_names,
        "means": [round(float(value), 10) for value in scaler.mean_],
        "scales": [round(float(value), 10) for value in scaler.scale_],
        "coefficients": [round(float(value), 10) for value in classifier.coef_[0]],
        "intercept": round(float(classifier.intercept_[0]), 10),
        "demoThresholds": dict(edge_config()["hazards"][hazard]),
        "syntheticGenerator": {
            "normalCenter": NORMAL[hazard],
            "eventCenter": EVENT[hazard],
            "scenarioGroups": 90,
            "windowsPerGroup": 12,
            "positiveWindowStartsAt": 6,
        },
        "training": {
            "seed": seed,
            "splitPolicy": "scenario-group 70/15/15",
            "trainScenarioGroups": len(set(groups[train_idx])),
            "validationScenarioGroups": len(set(groups[validation_idx])),
            "testScenarioGroups": len(set(groups[test_idx])),
            "trainWindows": len(train_idx),
            "validationWindows": len(validation_idx),
            "testWindows": len(test_idx),
            "syntheticOnly": True,
            "configSha256": hashlib.sha256(CONFIG_PATH.read_bytes()).hexdigest(),
        },
        "metrics": {
            "rulesOnly": _metrics(labels[test_idx], rule_probabilities),
            "classifierOnly": _metrics(labels[test_idx], classifier_probabilities),
            "rulesPlusClassifier": {
                **_metrics(labels[test_idx], fused_probabilities),
                "falseAlarmsPerSimulatedDay": round(false_positives / negative_days, 6),
                "missedEventRate": round(missed / max(1, len(positive_groups)), 6),
                "averageDetectionLeadTimeMinutes": round(float(np.mean(lead_times)) if lead_times else 0.0, 6),
            },
            "chronosAnomalyFeatures": {"status": "not_run"},
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Train deterministic synthetic edge risk baselines")
    parser.add_argument("--seed", type=int, default=20260902)
    parser.add_argument("--output", type=Path, default=MODEL_DIR)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    for offset, hazard in enumerate(FEATURES):
        artifact = train_hazard(hazard, args.seed + offset)
        target = args.output / f"{hazard}-demo-v1.json"
        target.write_text(json.dumps(artifact, indent=2) + "\n", encoding="utf-8")
        print(f"{hazard}: {artifact['metrics']['rulesPlusClassifier']}")


if __name__ == "__main__":
    main()
