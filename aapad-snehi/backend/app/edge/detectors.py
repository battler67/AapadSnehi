from __future__ import annotations

import json
import math
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

from .catalog import edge_config


MODEL_DIR = Path(__file__).resolve().parent / "model_artifacts"
HAZARDS = ("flood", "landslide", "tsunami")


@dataclass(frozen=True)
class DetectorResult:
    hazard: str
    probability: float
    risk_level: str
    confidence: float
    model_version: str
    model_status: str
    top_contributors: list[dict[str, float | str]]
    data_quality: float
    rule_score: float
    classifier_probability: float | None
    anomaly_score: float


def routed_hazards(device: Any) -> tuple[str, ...]:
    purposes = json.loads(device.installed_purposes_json)
    return tuple(hazard for hazard in HAZARDS if hazard in purposes)


def _scaled(value: float, start: float, full: float) -> float:
    if full <= start:
        return 0.0
    return max(0.0, min(1.0, (value - start) / (full - start)))


def _rule_components(hazard: str, features: dict[str, float]) -> list[tuple[str, float, float]]:
    if hazard == "flood":
        return [
            ("waterLevelM_current", _scaled(features.get("waterLevelM_current", 0), 3.5, 7.5), 0.30),
            ("waterLevelM_15m_slope", _scaled(features.get("waterLevelM_15m_slope", 0), 0.015, 0.12), 0.25),
            ("rainfall_accumulation_60m", _scaled(features.get("rainfall_accumulation_60m", 0), 20, 100), 0.20),
            ("soilMoisturePct_current", _scaled(features.get("soilMoisturePct_current", 0), 60, 95), 0.10),
            ("flowVelocityMps_current", _scaled(features.get("flowVelocityMps_current", 0), 1.5, 6), 0.10),
            ("flood_coupling", _scaled(features.get("flood_coupling", 0), 0.02, 0.5), 0.05),
        ]
    if hazard == "landslide":
        return [
            ("soilMoisturePct_current", _scaled(features.get("soilMoisturePct_current", 0), 60, 96), 0.20),
            ("poreWaterPressureKpa_current", _scaled(features.get("poreWaterPressureKpa_current", 0), 55, 180), 0.25),
            ("poreWaterPressureKpa_15m_slope", _scaled(features.get("poreWaterPressureKpa_15m_slope", 0), 0.2, 3), 0.15),
            ("tilt_vector_deg", _scaled(features.get("tilt_vector_deg", 0), 0.15, 2.5), 0.20),
            ("vibrationRmsMmS_current", _scaled(features.get("vibrationRmsMmS_current", 0), 3, 30), 0.10),
            ("rainfall_accumulation_60m", _scaled(features.get("rainfall_accumulation_60m", 0), 20, 90), 0.10),
        ]
    return [
        ("seaLevelAnomalyM_current", _scaled(abs(features.get("seaLevelAnomalyM_current", 0)), 0.08, 1.2), 0.30),
        ("seaLevelRateMPerMin_current", _scaled(abs(features.get("seaLevelRateMPerMin_current", 0)), 0.015, 0.18), 0.20),
        ("bottomPressureKpa_baseline_deviation", _scaled(abs(features.get("bottomPressureKpa_baseline_deviation", 0)), 0.5, 15), 0.20),
        ("waveHeightM_current", _scaled(features.get("waveHeightM_current", 0), 1.5, 8), 0.10),
        ("earthquakeMagnitude_current", _scaled(features.get("earthquakeMagnitude_current", 0), 5.5, 8.5), 0.15),
        ("tsunami_coupling", _scaled(features.get("tsunami_coupling", 0), 0.05, 1.5), 0.05),
    ]


def rule_score(hazard: str, features: dict[str, float]) -> tuple[float, list[dict[str, float | str]]]:
    parts = _rule_components(hazard, features)
    contributions = [
        {"feature": feature, "contribution": round(score * weight, 6)}
        for feature, score, weight in parts
        if score * weight > 0
    ]
    contributions.sort(key=lambda item: float(item["contribution"]), reverse=True)
    return round(sum(float(item["contribution"]) for item in contributions), 6), contributions


@lru_cache(maxsize=3)
def load_model(hazard: str) -> dict[str, Any] | None:
    path = MODEL_DIR / f"{hazard}-demo-v1.json"
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    required = {"modelVersion", "featureOrder", "means", "scales", "coefficients", "intercept"}
    if not required.issubset(payload) or payload.get("hazard") != hazard:
        return None
    feature_count = len(payload["featureOrder"])
    if any(len(payload[key]) != feature_count for key in ("means", "scales", "coefficients")):
        return None
    return payload


def classifier_score(
    hazard: str, features: dict[str, float]
) -> tuple[float | None, str, str, list[dict[str, float | str]]]:
    model = load_model(hazard)
    if model is None:
        return None, f"{hazard}-rules-v1", "fallback", []
    terms: list[tuple[str, float]] = []
    logit = float(model["intercept"])
    for name, mean, scale, coefficient in zip(
        model["featureOrder"], model["means"], model["scales"], model["coefficients"], strict=True
    ):
        normalized = (float(features.get(name, mean)) - float(mean)) / max(float(scale), 1e-9)
        contribution = normalized * float(coefficient)
        terms.append((name, contribution))
        logit += contribution
    probability = 1 / (1 + math.exp(-max(-40, min(40, logit))))
    contributors = [
        {"feature": name, "contribution": round(value, 6)}
        for name, value in sorted(terms, key=lambda item: abs(item[1]), reverse=True)[:5]
    ]
    return probability, str(model["modelVersion"]), "loaded", contributors


def evaluate_hazard(
    hazard: str,
    features: dict[str, float],
    *,
    data_quality: float,
    anomaly_score: float,
    geographic_relevance: float,
    agreement_count: int = 0,
) -> DetectorResult:
    rules, rule_contributors = rule_score(hazard, features)
    classifier, model_version, model_status, model_contributors = classifier_score(hazard, features)
    weights = edge_config()["fusion"]
    parts = [
        (rules, float(weights["ruleWeight"])),
        (anomaly_score, float(weights["anomalyWeight"])),
    ]
    if classifier is not None:
        parts.append((classifier, float(weights["classifierWeight"])))
    fused = sum(value * weight for value, weight in parts) / sum(weight for _, weight in parts)
    quality_factor = 0.6 + 0.4 * max(0.0, min(1.0, data_quality))
    agreement_factor = 1.08 if agreement_count >= 2 else 1.03 if agreement_count == 1 else 0.96
    probability = max(0.0, min(1.0, fused * quality_factor * geographic_relevance * agreement_factor))
    policy = edge_config()["hazards"][hazard]
    risk_level = (
        "CRITICAL" if probability >= policy["critical"] else
        "WARNING" if probability >= policy["warning"] else
        "WATCH" if probability >= policy["watch"] else "NORMAL"
    )
    agreement_confidence = min(1.0, 0.75 + 0.1 * agreement_count)
    model_factor = 1.0 if classifier is not None else 0.82
    confidence = max(0.0, min(1.0, data_quality * agreement_confidence * model_factor))
    contributors = sorted(
        [*rule_contributors, *model_contributors],
        key=lambda item: abs(float(item["contribution"])),
        reverse=True,
    )[:5]
    return DetectorResult(
        hazard=hazard,
        probability=round(probability, 6),
        risk_level=risk_level,
        confidence=round(confidence, 6),
        model_version=model_version,
        model_status=model_status,
        top_contributors=contributors,
        data_quality=round(data_quality, 6),
        rule_score=rules,
        classifier_probability=round(classifier, 6) if classifier is not None else None,
        anomaly_score=round(anomaly_score, 6),
    )
