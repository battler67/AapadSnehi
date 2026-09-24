from __future__ import annotations

import math
import time
from datetime import datetime, timedelta, timezone
from typing import Any

import numpy as np

from .registry import FLOOD_DYNAMIC_DETAILS, WILDFIRE_DETAILS, ModelRegistry
from .schemas import PredictionRequest


SUPPORTED_CATCHMENTS = {
    "03005", "03008", "03013", "03040", "03048", "03094", "04004", "04007",
    "04012", "04021", "04022", "04026", "04028", "04030", "04038", "04054",
    "04061", "04062", "04063", "04064", "05002", "05010", "05013", "05018",
    "05022", "06001", "07002", "07005", "07007", "07008",
}

WILDFIRE_CHANNELS = tuple(WILDFIRE_DETAILS)
WILDFIRE_STATS = {
    "elevation": (0.0, 3141.0, 657.0, 649.0),
    "pdsi": (-6.1, 7.9, 0.0, 2.7),
    "NDVI": (-9821.0, 9996.0, 5158.0, 2467.0),
    "pr": (0.0, 44.5, 1.7, 4.5),
    "sph": (0.0, 1.0, 0.0072, 0.0043),
    "th": (0.0, 360.0, 190.3, 72.6),
    "tmmn": (253.2, 298.9, 281.1, 9.0),
    "tmmx": (253.2, 315.1, 295.2, 9.8),
    "vs": (0.0, 10.0, 3.9, 1.4),
    "erc": (0.0, 106.0, 37.0, 21.0),
    "population": (0.0, 2534.0, 26.0, 155.0),
    "PrevFireMask": (-1.0, 1.0, 0.0, 1.0),
}


class MLValidationError(ValueError):
    pass


class MLUnavailableError(RuntimeError):
    pass


def _timing(request: PredictionRequest) -> tuple[datetime, list[str]]:
    now = datetime.now(timezone.utc)
    issue = request.prediction_time or now
    available = request.latest_input_available_at or issue
    observed = request.latest_observation_time or (available - timedelta(minutes=1))
    warnings = []
    if request.prediction_time is None:
        warnings.append("Prediction and availability times were assumed at request receipt for this manual/synthetic demonstration.")
    if available > issue:
        raise MLValidationError("latestInputAvailableAt cannot be after predictionTime")
    if observed > available:
        raise MLValidationError("latestObservationTime cannot be after latestInputAvailableAt")
    if issue - observed > timedelta(days=1):
        raise MLValidationError("Required daily observations are stale by more than one day")
    return issue, warnings


def _number(value: Any, name: str, *, absolute_limit: float = 1_000_000_000.0) -> float:
    if isinstance(value, bool):
        raise MLValidationError(f"{name} must be a number, not a Boolean")
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise MLValidationError(f"{name} must be a finite number") from exc
    if not math.isfinite(number) or abs(number) > absolute_limit:
        raise MLValidationError(f"{name} must be a finite value within the supported payload bounds")
    return number


class MLInferenceService:
    def __init__(self, registry: ModelRegistry) -> None:
        self.registry = registry

    def predict(self, request: PredictionRequest) -> dict[str, Any]:
        if request.source not in {"manual", "synthetic"}:
            raise MLValidationError(f"Source '{request.source}' is reserved for a future adapter and is not connected")
        if not request.units_confirmed:
            raise MLValidationError("unitsConfirmed must be true after checking every dataset-native input unit")
        try:
            definition = self.registry.definition(request.model_id)
        except KeyError as exc:
            raise MLValidationError(str(exc)) from exc
        issue, warnings = _timing(request)
        started = time.perf_counter()
        try:
            loaded = self.registry.load(request.model_id)
        except Exception as exc:
            raise MLUnavailableError("The selected trusted model is unavailable in this runtime") from exc
        try:
            if definition.kind == "wildfire":
                result = self._predict_wildfire(loaded, request.features, warnings)
            else:
                result = self._predict_flood(definition.kind, loaded, request.features, warnings)
        except (MLValidationError, MLUnavailableError):
            raise
        except Exception as exc:
            raise MLUnavailableError(
                "The selected trusted model could not run in this runtime"
            ) from exc
        elapsed_ms = (time.perf_counter() - started) * 1000
        return {
            "status": "prediction",
            "modelId": request.model_id,
            "modelName": definition.name,
            "modelVersion": result.pop("modelVersion"),
            "target": definition.target,
            "source": request.source,
            "synthetic": request.source == "synthetic",
            "predictionTime": issue.isoformat(),
            "horizon": "one dataset day",
            "predictedOutcome": result.pop("predictedOutcome"),
            "confidence": result.pop("confidence", None),
            "riskLevel": result.pop("riskLevel"),
            "classProbabilities": result.pop("classProbabilities", None),
            "inputDataUsed": result.pop("inputDataUsed"),
            "outputDetails": result,
            "validationWarnings": warnings,
            "limitations": list(definition.limitations),
            "operationallyValidated": False,
            "inferenceTimeMs": round(elapsed_ms, 3),
        }

    def _predict_flood(
        self,
        kind: str,
        saved: dict[str, Any],
        features: dict[str, Any],
        warnings: list[str],
    ) -> dict[str, Any]:
        import pandas as pd

        row = features.get("row")
        if not isinstance(row, dict):
            raise MLValidationError("features.row must be one complete engineered catchment-day object")
        columns = list(saved.get("feature_columns", saved.get("features", [])))
        missing = [name for name in columns if name not in row or row[name] is None]
        if missing:
            raise MLValidationError("Missing required features: " + ", ".join(missing[:8]) + ("…" if len(missing) > 8 else ""))
        forbidden = sorted(set(row) - set(columns))
        if forbidden:
            raise MLValidationError("Unexpected or target-like features: " + ", ".join(forbidden[:8]))
        catchment = str(row["catchment_id"])
        if catchment not in SUPPORTED_CATCHMENTS:
            raise MLValidationError("Unseen catchment; generalisation is not validated")
        clean: dict[str, Any] = {"catchment_id": catchment}
        for name in columns:
            if name == "catchment_id":
                continue
            value = _number(row[name], name)
            clean[name] = value
            details = FLOOD_DYNAMIC_DETAILS.get(name)
            if details and ((details[2] is not None and value < details[2]) or (details[3] is not None and value > details[3])):
                warnings.append(f"{details[0]} is outside the documented selected-row range; review for distribution shift.")
        frame = pd.DataFrame([clean], columns=columns)
        model = saved["model"]
        if kind == "flood_classifier":
            probability = float(model.predict_proba(frame)[0, 1])
            if "calibrator" in saved:
                clipped = np.clip(probability, 1e-6, 1 - 1e-6)
                probability = float(saved["calibrator"].predict_proba(np.log(clipped / (1 - clipped)).reshape(-1, 1))[0, 1])
            cutoff = float(saved["threshold"])
            flagged = probability >= cutoff
            return {
                "modelVersion": str(saved["version"]),
                "predictedOutcome": "Above research review cutoff" if flagged else "Below research review cutoff",
                "confidence": None,
                "riskLevel": "research_review" if flagged else "below_review_cutoff_not_safe",
                "classProbabilities": {"notHighFlow": 1 - probability, "highFlow": probability},
                "inputDataUsed": clean,
                "highFlowScore": probability,
                "validationAlertCutoff": cutoff,
                "reviewFlag": flagged,
                "scoreMeaning": "Validation-calibrated training-q95 exceedance score; not inundation probability.",
            }
        discharge = float(max(0.0, model.predict(frame)[0]))
        if not math.isfinite(discharge):
            raise MLUnavailableError("Model returned a non-finite discharge estimate")
        return {
            "modelVersion": str(saved["version"]),
            "predictedOutcome": f"Estimated next-day discharge: {discharge:.3f} m³/s",
            "riskLevel": "not_assessed",
            "inputDataUsed": clean,
            "dischargeM3S": discharge,
            "uncertainty": "No calibrated confidence interval is available.",
        }

    def _predict_wildfire(
        self,
        loaded: dict[str, Any],
        features: dict[str, Any],
        warnings: list[str],
    ) -> dict[str, Any]:
        import torch

        channels = features.get("channels")
        if not isinstance(channels, dict):
            raise MLValidationError("features.channels must contain all twelve aligned 64×64 grids")
        missing = [name for name in WILDFIRE_CHANNELS if name not in channels]
        extra = sorted(set(channels) - set(WILDFIRE_CHANNELS))
        if missing:
            raise MLValidationError("Missing wildfire channels: " + ", ".join(missing))
        if extra:
            raise MLValidationError("Unexpected wildfire channels: " + ", ".join(extra))
        raw: dict[str, np.ndarray] = {}
        summaries: dict[str, Any] = {}
        normalized = []
        for name in WILDFIRE_CHANNELS:
            try:
                value = np.asarray(channels[name], dtype=np.float32)
            except (TypeError, ValueError) as exc:
                raise MLValidationError(f"{name} must be a numeric 64×64 grid") from exc
            if value.shape != (64, 64):
                raise MLValidationError(f"{name} must have shape 64×64")
            if not np.isfinite(value).all() or float(np.max(np.abs(value))) > 10_000_000:
                raise MLValidationError(f"{name} contains non-finite or unsupported values")
            raw[name] = value
            summaries[name] = {
                "shape": [64, 64],
                "minimum": float(value.min()),
                "maximum": float(value.max()),
                "mean": float(value.mean()),
                "unit": WILDFIRE_DETAILS[name][1],
            }
            if name == "PrevFireMask":
                if not np.isin(value, [-1, 0, 1]).all():
                    raise MLValidationError("PrevFireMask accepts only -1, 0, or 1")
                normalized.append(value)
                continue
            low, high, mean, std = WILDFIRE_STATS[name]
            if bool((value < low).any() or (value > high).any()):
                warnings.append(f"{WILDFIRE_DETAILS[name][0]} includes values outside the training clip range and was clipped.")
            normalized.append((np.clip(value, low, high) - mean) / std)
        if not bool((raw["PrevFireMask"] == 1).any()):
            raise MLValidationError("No known existing fire is present; ignition prediction is outside model scope")
        tensor = torch.from_numpy(np.stack(normalized, dtype=np.float32)[None])
        with torch.inference_mode():
            score_map = torch.sigmoid(loaded["model"](tensor))[0].cpu().numpy()
        if score_map.shape != (64, 64) or not np.isfinite(score_map).all():
            raise MLUnavailableError("Model returned an invalid score grid")
        threshold = float(loaded["threshold"])
        predicted = score_map >= threshold
        known_inactive = raw["PrevFireMask"] == 0
        new_cells = int((predicted & known_inactive).sum())
        active_cells = int(predicted.sum())
        return {
            "modelVersion": "wildfire-screen-unet-b16-s42",
            "predictedOutcome": f"{active_cells} cells above the validation-selected activity cutoff",
            "riskLevel": "research_review" if new_cells else "no_new_cells_flagged_not_safe",
            "inputDataUsed": {"channels": summaries, "existingActiveCells": int((raw["PrevFireMask"] == 1).sum())},
            "scoreMap": score_map.tolist(),
            "scoreSummary": {
                "minimum": float(score_map.min()),
                "maximum": float(score_map.max()),
                "mean": float(score_map.mean()),
            },
            "validationAlertCutoff": threshold,
            "cellsAboveCutoff": active_cells,
            "newlyActiveCandidateCells": new_cells,
            "scoreMeaning": "Uncalibrated model score; not a verified probability or geographic fire perimeter.",
        }
