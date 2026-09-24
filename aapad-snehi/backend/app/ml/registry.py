from __future__ import annotations

import hashlib
import importlib.util
from importlib import metadata
import json
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .scenarios import scenario_catalog


MODEL_IDS = (
    "flood-random-forest-v2",
    "flood-xgboost-event-v2",
    "wildfire-unet-v1",
)

FLOOD_RUNTIME_VERSIONS = {
    "scikit-learn": "1.7.1",
}
XGBOOST_RUNTIME_VERSION = "3.0.4"

FLOOD_DYNAMIC_DETAILS: dict[str, tuple[str, str, float | None, float | None, str]] = {
    "prcp(mm/day)": ("Daily precipitation", "mm/day", 0.0, 244.67, "Catchment-average precipitation for source day t."),
    "tavg(C)": ("Average temperature", "°C", 10.82, 39.1, "Catchment-average daily air temperature."),
    "rel_hum(%)": ("Relative humidity", "%", 5.31, 99.47, "Catchment-average relative humidity at 2 m."),
    "sm_lvl1(kg/m2)": ("Soil water layer 1", "kg/m²", 1.82, 46.18, "IMDAA 0–0.1 m layer; not sensor moisture percent."),
    "sm_lvl2(kg/m2)": ("Soil water layer 2", "kg/m²", 47.17, 115.96, "IMDAA 0.1–0.35 m layer."),
    "sm_lvl3(kg/m2)": ("Soil water layer 3", "kg/m²", 111.36, 280.11, "IMDAA 0.35–1 m layer."),
    "sm_lvl4(kg/m2)": ("Soil water layer 4", "kg/m²", 407.75, 751.34, "IMDAA 1–3 m layer."),
    "discharge": ("Current discharge", "m³/s", 0.0, None, "Observed catchment outlet discharge on source day t."),
    "discharge_lag_1": ("Discharge lag 1", "m³/s", 0.0, None, "Legacy schema: lag 1 equals current q[t]."),
    "discharge_lag_2": ("Discharge lag 2", "m³/s", 0.0, None, "Observed q[t-1]."),
    "discharge_lag_3": ("Discharge lag 3", "m³/s", 0.0, None, "Observed q[t-2]."),
    "discharge_lag_7": ("Discharge lag 7", "m³/s", 0.0, None, "Observed historical discharge using the saved legacy lag naming."),
    "discharge_lag_14": ("Discharge lag 14", "m³/s", 0.0, None, "Observed historical discharge using the saved legacy lag naming."),
    "discharge_lag_30": ("Discharge lag 30", "m³/s", 0.0, None, "Observed historical discharge using the saved legacy lag naming."),
    "rain_sum_3": ("3-day rainfall total", "mm", 0.0, None, "Sum through source day t."),
    "rain_sum_7": ("7-day rainfall total", "mm", 0.0, None, "Sum through source day t."),
    "rain_sum_14": ("14-day rainfall total", "mm", 0.0, None, "Sum through source day t."),
    "rain_sum_30": ("30-day rainfall total", "mm", 0.0, None, "Sum through source day t."),
    "discharge_trend_3": ("3-day discharge trend", "m³/s", None, None, "q[t] minus q[t-3]."),
    "discharge_trend_7": ("7-day discharge trend", "m³/s", None, None, "q[t] minus q[t-7]."),
    "season_sin": ("Season sine", "ratio", -1.0, 1.0, "sin(2π × day-of-year / 365.25)."),
    "season_cos": ("Season cosine", "ratio", -1.0, 1.0, "cos(2π × day-of-year / 365.25)."),
}

WILDFIRE_DETAILS: dict[str, tuple[str, str, float, float, str]] = {
    "elevation": ("Elevation", "m", 0.0, 3141.0, "Values outside this training clip range are clipped."),
    "pdsi": ("Palmer drought severity index", "index", -6.1, 7.9, "Dataset-native drought index."),
    "NDVI": ("Vegetation index", "native scaled index", -9821.0, 9996.0, "Do not convert automatically to 0–1."),
    "pr": ("Daily precipitation", "mm/day", 0.0, 44.5, "Aligned current-day grid."),
    "sph": ("Specific humidity", "kg/kg", 0.0, 1.0, "Not relative humidity percent."),
    "th": ("Wind direction", "degrees", 0.0, 360.0, "Clockwise from north."),
    "tmmn": ("Minimum temperature", "K", 253.2, 298.9, "Kelvin, not Celsius."),
    "tmmx": ("Maximum temperature", "K", 253.2, 315.1, "Kelvin, not Celsius."),
    "vs": ("Wind speed", "m/s", 0.0, 10.0, "Aligned current-day wind-speed grid."),
    "erc": ("Energy Release Component", "index", 0.0, 106.0, "Dataset-supplied fire-weather index."),
    "population": ("Population density", "people/km²", 0.0, 2534.0, "Aligned population-density grid."),
    "PrevFireMask": ("Current active-fire mask", "-1 unknown, 0 inactive, 1 active", -1.0, 1.0, "Must contain at least one known active-fire cell."),
}


@dataclass(frozen=True)
class ModelDefinition:
    model_id: str
    manifest_key: str
    name: str
    disaster: str
    target: str
    description: str
    artifact_path: str
    sha256: str
    kind: str
    supported_output: str
    limitations: tuple[str, ...]


DEFINITIONS = {
    "flood-random-forest-v2": ModelDefinition(
        "flood-random-forest-v2",
        "random_forest",
        "Random Forest discharge",
        "flood",
        "Next-day catchment discharge",
        "Estimates next-day observed outlet discharge for one supported CAMELS-IND catchment-day.",
        "artifacts/flood/selected_regression.joblib",
        "c4251a733ed3d7254a9c0dcd89d796b9ce9900c72bfe8e9b01c8bfab0d085fe9",
        "flood_regression",
        "Non-negative discharge estimate in m³/s",
        (
            "Historical CAMELS-IND research model for 30 supported catchments; not field-validated.",
            "Does not predict water level, flood extent, casualties, or a calibrated uncertainty interval.",
            "Static attributes and retrospective forcings may not have been operationally available on the historical issue date.",
        ),
    ),
    "flood-xgboost-event-v2": ModelDefinition(
        "flood-xgboost-event-v2",
        "xgboost",
        "XGBoost high-flow review",
        "flood",
        "Next-day training-q95 exceedance",
        "Returns a calibrated research score for unusually high next-day catchment flow.",
        "artifacts/flood/selected_event.joblib",
        "041c08e0472d57d91b67c67c68f5778f541613fe2a77b7a224a379c44dcaf714",
        "flood_classifier",
        "High-flow score and validation-cutoff review flag",
        (
            "The physical target is a catchment training-period q95, not an official flood or danger threshold.",
            "About half of held-out research flags were false positives at the recall-oriented cutoff.",
            "A below-cutoff result must not be interpreted as safe.",
        ),
    ),
    "wildfire-unet-v1": ModelDefinition(
        "wildfire-unet-v1",
        "unet",
        "Compact U-Net fire activity",
        "wildfire",
        "Next-day active-fire score grid",
        "Produces a 64×64 next-day activity score map around a known existing fire.",
        "runs/wildfire/screening/dl/wildfire-screen-unet-b16-s42/best.pt",
        "dcb6ad6e5ed7e7d0552fc0ea147fadf0810d845503421e4269de684b82a41639",
        "wildfire",
        "Uncalibrated score map and validation-cutoff cell mask",
        (
            "US research scenes are not validated for Indian forests or ignition prediction.",
            "Scores are uncalibrated and the held-out precision was low; do not interpret them as fire probabilities.",
            "Scenes lack coordinates, dates, and independent-fire IDs, so the grid is not a geographic perimeter.",
        ),
    ),
}


class ModelRegistry:
    def __init__(self, root: Path) -> None:
        self.root = root.resolve()
        self._models: dict[str, Any] = {}
        self._hashes: dict[str, str] = {}
        self._errors: dict[str, str] = {}
        self._lock = threading.RLock()

    def artifact_path(self, model_id: str) -> Path:
        definition = self.definition(model_id)
        candidate = (self.root / definition.artifact_path).resolve()
        if not candidate.is_relative_to(self.root):
            raise ValueError("Model artifact escaped the approved root")
        return candidate

    @staticmethod
    def definition(model_id: str) -> ModelDefinition:
        try:
            return DEFINITIONS[model_id]
        except KeyError as exc:
            raise KeyError("Unknown allowlisted model") from exc

    def _dependency_status(self, definition: ModelDefinition) -> str | None:
        required = ["numpy"]
        if definition.kind.startswith("flood"):
            required.extend(["joblib", "pandas", "sklearn"])
        if definition.kind == "flood_classifier":
            required.append("xgboost")
        if definition.kind == "wildfire":
            required.append("torch")
        missing = [name for name in required if importlib.util.find_spec(name) is None]
        if missing:
            return f"Missing runtime dependencies: {', '.join(missing)}"
        if definition.kind.startswith("flood"):
            mismatches = []
            for package, expected in FLOOD_RUNTIME_VERSIONS.items():
                installed = metadata.version(package)
                if installed != expected:
                    mismatches.append(f"{package} {installed} (requires {expected})")
            if definition.kind == "flood_classifier":
                installed = metadata.version("xgboost")
                if installed != XGBOOST_RUNTIME_VERSION:
                    mismatches.append(
                        f"xgboost {installed} (requires {XGBOOST_RUNTIME_VERSION})"
                    )
            if mismatches:
                return "Incompatible model runtime: " + ", ".join(mismatches)
        return None

    def verify(self, model_id: str) -> dict[str, Any]:
        definition = self.definition(model_id)
        dependency_error = self._dependency_status(definition)
        if dependency_error:
            unavailable_status = (
                "runtime_incompatible"
                if dependency_error.startswith("Incompatible model runtime:")
                else "dependency_missing"
            )
            return {
                "available": False,
                "status": unavailable_status,
                "detail": dependency_error,
            }
        path = self.artifact_path(model_id)
        if not path.is_file():
            return {"available": False, "status": "artifact_missing", "detail": "Configured model artifact is unavailable"}
        with self._lock:
            digest = self._hashes.get(model_id)
            if digest is None:
                with path.open("rb") as stream:
                    digest = hashlib.file_digest(stream, "sha256").hexdigest()
                self._hashes[model_id] = digest
        if digest != definition.sha256:
            return {"available": False, "status": "checksum_mismatch", "detail": "Model artifact integrity check failed"}
        return {
            "available": True,
            "status": "loaded" if model_id in self._models else "verified_not_loaded",
            "detail": "Ready",
            "sha256": digest,
        }

    def load(self, model_id: str) -> Any:
        with self._lock:
            if model_id in self._models:
                return self._models[model_id]
            status = self.verify(model_id)
            if not status["available"]:
                self._errors[model_id] = status["detail"]
                raise RuntimeError(status["detail"])
            definition = self.definition(model_id)
            path = self.artifact_path(model_id)
            if definition.kind.startswith("flood"):
                import joblib

                loaded = joblib.load(path)
            else:
                loaded = self._load_unet(path)
            self._models[model_id] = loaded
            self._errors.pop(model_id, None)
            return loaded

    @staticmethod
    def _load_unet(path: Path) -> dict[str, Any]:
        import torch
        from torch import nn

        class Block(nn.Module):
            def __init__(self, inputs: int, outputs: int) -> None:
                super().__init__()
                self.net = nn.Sequential(
                    nn.Conv2d(inputs, outputs, 3, padding=1),
                    nn.BatchNorm2d(outputs),
                    nn.ReLU(),
                    nn.Conv2d(outputs, outputs, 3, padding=1),
                    nn.BatchNorm2d(outputs),
                    nn.ReLU(),
                )

            def forward(self, value):
                return self.net(value)

        class UNet(nn.Module):
            def __init__(self, base: int) -> None:
                super().__init__()
                self.e1 = Block(12, base)
                self.e2 = Block(base, base * 2)
                self.bottom = Block(base * 2, base * 4)
                self.pool = nn.MaxPool2d(2)
                self.up2 = nn.ConvTranspose2d(base * 4, base * 2, 2, 2)
                self.d2 = Block(base * 4, base * 2)
                self.up1 = nn.ConvTranspose2d(base * 2, base, 2, 2)
                self.d1 = Block(base * 2, base)
                self.out = nn.Conv2d(base, 1, 1)

            def forward(self, value):
                e1 = self.e1(value)
                e2 = self.e2(self.pool(e1))
                value = self.bottom(self.pool(e2))
                value = self.d2(torch.cat([self.up2(value), e2], 1))
                value = self.d1(torch.cat([self.up1(value), e1], 1))
                return self.out(value).squeeze(1)

        saved = torch.load(path, map_location="cpu", weights_only=False)
        model = UNet(int(saved["config"]["base_channels"]))
        model.load_state_dict(saved["state_dict"])
        model.eval()
        return {"model": model, "threshold": float(saved["threshold"]), "config": saved["config"]}

    def feature_schema(self, model_id: str) -> list[dict[str, Any]]:
        definition = self.definition(model_id)
        if definition.kind == "wildfire":
            return [
                {
                    "name": name,
                    "label": details[0],
                    "type": "integer_grid" if name == "PrevFireMask" else "number_grid",
                    "unit": details[1],
                    "minimum": details[2],
                    "maximum": details[3],
                    "shape": [64, 64],
                    "helperText": details[4],
                    "required": True,
                    "group": "Current fire" if name == "PrevFireMask" else "Environmental grid",
                }
                for name, details in WILDFIRE_DETAILS.items()
            ]
        manifest_path = self.root / "reports" / "model_handoff_manifest.json"
        if not manifest_path.is_file():
            return []
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        columns = manifest["models"][definition.manifest_key]["feature_columns"]
        schema = []
        for name in columns:
            if name == "catchment_id":
                schema.append({
                    "name": name,
                    "label": "Supported catchment ID",
                    "type": "string",
                    "unit": "CAMELS-IND ID",
                    "minimum": None,
                    "maximum": None,
                    "helperText": "Preserve leading zeros. Only the 30 trained catchments are accepted.",
                    "required": True,
                    "group": "Catchment identity",
                })
                continue
            details = FLOOD_DYNAMIC_DETAILS.get(name)
            label = details[0] if details else name.replace("_", " ").replace("ghi ", "GHI ").replace("cwc ", "CWC ").title()
            schema.append({
                "name": name,
                "label": label,
                "type": "number",
                "unit": details[1] if details else "dataset-native",
                "minimum": details[2] if details else None,
                "maximum": details[3] if details else None,
                "helperText": details[4] if details else "Use the exact historical catchment attribute; a validated manual range is not documented.",
                "required": True,
                "group": "Dynamic and engineered" if details else "Static catchment attributes",
            })
        return schema

    def catalog(self) -> dict[str, Any]:
        models = []
        for model_id, definition in DEFINITIONS.items():
            status = self.verify(model_id)
            manifest = {}
            manifest_path = self.root / "reports" / "model_handoff_manifest.json"
            if manifest_path.is_file():
                manifest = json.loads(manifest_path.read_text(encoding="utf-8"))["models"].get(definition.manifest_key, {})
            features = self.feature_schema(model_id)
            if definition.kind.startswith("flood") and not features:
                status = {
                    "available": False,
                    "status": "metadata_missing",
                    "detail": "Configured model feature metadata is unavailable",
                }
            models.append({
                "id": model_id,
                "name": definition.name,
                "disaster": definition.disaster,
                "target": definition.target,
                "description": definition.description,
                "version": manifest.get("version", "unknown"),
                "inputMode": "spatial_grid" if definition.kind == "wildfire" else "engineered_row",
                "features": features,
                "supportedOutput": definition.supported_output,
                "limitations": list(definition.limitations),
                "scenarios": scenario_catalog(definition.disaster),
                "availability": status,
                "operationallyValidated": False,
            })
        return {
            "apiVersion": "v1",
            "notice": "Historical research demonstration — not an official warning or live sensor forecast.",
            "models": models,
            "unavailableModels": [{
                "id": "landslide",
                "reason": "No landslide model was trained because source and label quality did not pass the research gate.",
            }],
            "supportedSources": ["manual", "synthetic"],
            "futureSources": ["weather_api", "iot_sensor", "edge_device", "official_disaster_api"],
        }

    def health(self) -> dict[str, Any]:
        return {
            "status": "ready" if any(self.verify(model_id)["available"] for model_id in MODEL_IDS) else "unavailable",
            "models": {model_id: self.verify(model_id) for model_id in MODEL_IDS},
            "loadedModelIds": sorted(self._models),
        }
