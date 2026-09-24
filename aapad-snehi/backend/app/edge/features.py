from __future__ import annotations

import math
import statistics
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

from .catalog import edge_config, property_definition


FEATURE_PIPELINE_VERSION = "edge-features-v1"


@dataclass(frozen=True)
class FeatureResult:
    as_of: datetime
    features: dict[str, float]
    observation_ids: list[int]
    data_quality: float
    anomaly_score: float


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _linear_slope(samples: list[tuple[datetime, float]]) -> float:
    if len(samples) < 2:
        return 0.0
    origin = _utc(samples[0][0])
    xs = [(_utc(timestamp) - origin).total_seconds() / 60 for timestamp, _ in samples]
    ys = [value for _, value in samples]
    x_mean = statistics.fmean(xs)
    y_mean = statistics.fmean(ys)
    denominator = sum((x - x_mean) ** 2 for x in xs)
    if denominator <= 0:
        return 0.0
    return sum((x - x_mean) * (y - y_mean) for x, y in zip(xs, ys, strict=True)) / denominator


def _ewma(values: list[float], alpha: float = 0.35) -> float:
    if not values:
        return 0.0
    result = values[0]
    for value in values[1:]:
        result = alpha * value + (1 - alpha) * result
    return result


def _bounded(value: float) -> float:
    return round(max(0.0, min(1.0, value)), 6)


def build_features(
    observations: list[dict[str, Any]],
    *,
    capabilities: list[str],
    as_of: datetime,
    expected_interval_seconds: int = 60,
) -> FeatureResult:
    """Build event-time features using only observations at or before ``as_of``."""

    as_of = _utc(as_of)
    eligible = sorted(
        (
            observation
            for observation in observations
            if _utc(observation["timestamp"]) <= as_of
            and _utc(observation["timestamp"]) >= as_of - timedelta(minutes=60)
        ),
        key=lambda item: (_utc(item["timestamp"]), item.get("id", 0)),
    )
    features: dict[str, float] = {}
    windows = edge_config()["windowsMinutes"]

    for property_name in capabilities:
        all_samples = [
            (_utc(item["timestamp"]), float(item["measurements"][property_name]))
            for item in eligible
            if item["measurements"].get(property_name) is not None
        ]
        if all_samples:
            features[f"{property_name}_current"] = all_samples[-1][1]
            prior = [value for _, value in all_samples[:-1]]
            baseline = statistics.fmean(prior) if prior else all_samples[-1][1]
            features[f"{property_name}_baseline_deviation"] = all_samples[-1][1] - baseline
        else:
            features[f"{property_name}_current"] = 0.0
            features[f"{property_name}_baseline_deviation"] = 0.0

        for minutes in windows:
            cutoff = as_of - timedelta(minutes=minutes)
            samples = [(timestamp, value) for timestamp, value in all_samples if timestamp >= cutoff]
            values = [value for _, value in samples]
            prefix = f"{property_name}_{minutes}m"
            if values:
                features[f"{prefix}_mean"] = statistics.fmean(values)
                features[f"{prefix}_min"] = min(values)
                features[f"{prefix}_max"] = max(values)
                features[f"{prefix}_std"] = statistics.pstdev(values) if len(values) > 1 else 0.0
                features[f"{prefix}_slope"] = _linear_slope(samples)
                features[f"{prefix}_ewma"] = _ewma(values)
                features[f"{prefix}_rate"] = _linear_slope(samples[-2:])
                if len(samples) >= 3:
                    first_rate = _linear_slope(samples[-3:-1])
                    second_rate = _linear_slope(samples[-2:])
                    features[f"{prefix}_acceleration"] = second_rate - first_rate
                else:
                    features[f"{prefix}_acceleration"] = 0.0
            else:
                for suffix in ("mean", "min", "max", "std", "slope", "ewma", "rate", "acceleration"):
                    features[f"{prefix}_{suffix}"] = 0.0

            definition = property_definition(property_name) or {}
            threshold = definition.get("warning")
            consecutive = 0
            if threshold is not None:
                for value in reversed(values):
                    abnormal = abs(value) >= float(threshold) if property_name.startswith("groundTilt") else value >= float(threshold)
                    if not abnormal:
                        break
                    consecutive += 1
            features[f"{prefix}_consecutive_exceedances"] = float(consecutive)

    rainfall = [
        float(item["measurements"]["rainfallMmH"])
        for item in eligible
        if item["measurements"].get("rainfallMmH") is not None
    ]
    features["rainfall_accumulation_60m"] = sum(rainfall) * expected_interval_seconds / 3600
    tilt_x = features.get("groundTiltXDeg_current", 0.0)
    tilt_y = features.get("groundTiltYDeg_current", 0.0)
    features["tilt_vector_deg"] = math.hypot(tilt_x, tilt_y)
    features["flood_coupling"] = max(0.0, features.get("waterLevelM_15m_slope", 0.0)) * (
        1 + max(0.0, features.get("rainfallMmH_30m_mean", 0.0)) / 50
    )
    features["landslide_coupling"] = (
        max(0.0, features.get("soilMoisturePct_current", 0.0) - 60) / 40
        + max(0.0, features.get("poreWaterPressureKpa_15m_slope", 0.0)) / 5
        + features["tilt_vector_deg"]
    )
    features["tsunami_coupling"] = abs(features.get("seaLevelAnomalyM_current", 0.0)) * (
        1 + abs(features.get("seaLevelRateMPerMin_current", 0.0)) * 5
    )

    expected_samples = max(1, int(3600 / max(1, expected_interval_seconds)) + 1)
    expected_values = max(1, expected_samples * max(1, len(capabilities)))
    present_values = sum(
        1
        for item in eligible
        for capability in capabilities
        if item["measurements"].get(capability) is not None
    )
    completeness = min(1.0, present_values / expected_values)
    health_values = [
        (float(item.get("batteryPct", 100)) + float(item.get("signalQualityPct", 100))) / 200
        for item in eligible
    ]
    health = statistics.fmean(health_values) if health_values else 0.0
    flag_count = sum(len(item.get("qualityFlags", [])) for item in eligible)
    integrity = max(0.0, 1 - flag_count / max(1, len(eligible) * 3))
    data_quality = _bounded(0.5 * completeness + 0.3 * health + 0.2 * integrity)
    features["missing_data_pct"] = round(100 * (1 - completeness), 6)
    features["device_health_score"] = round(health, 6)

    residuals: list[float] = []
    for property_name in capabilities:
        current = features.get(f"{property_name}_current", 0.0)
        predicted = features.get(f"{property_name}_15m_ewma", current) + features.get(
            f"{property_name}_15m_slope", 0.0
        )
        scale = max(0.01, features.get(f"{property_name}_30m_std", 0.0))
        residuals.append(abs(current - predicted) / (3 * scale + abs(current) * 0.02 + 0.01))
    anomaly_score = _bounded(statistics.fmean(min(1.0, value) for value in residuals) if residuals else 0.0)
    features["forecast_residual_anomaly"] = anomaly_score

    return FeatureResult(
        as_of=as_of,
        features={key: round(value, 6) for key, value in features.items() if math.isfinite(value)},
        observation_ids=[int(item["id"]) for item in eligible if item.get("id") is not None],
        data_quality=data_quality,
        anomaly_score=anomaly_score,
    )
