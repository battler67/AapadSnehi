from __future__ import annotations

import math
import os
from dataclasses import dataclass
from typing import Protocol


class ForecastAdapter(Protocol):
    name: str

    def anomaly_score(self, values: list[float]) -> float: ...


@dataclass
class RollingForecastAdapter:
    name: str = "rolling-linear-ewma-v1"

    def anomaly_score(self, values: list[float]) -> float:
        if len(values) < 4:
            return 0.0
        history = values[:-1]
        latest = values[-1]
        slope = (history[-1] - history[0]) / max(1, len(history) - 1)
        trend_forecast = history[-1] + slope
        ewma = history[0]
        for value in history[1:]:
            ewma = 0.35 * value + 0.65 * ewma
        forecast = 0.6 * trend_forecast + 0.4 * ewma
        mean = sum(history) / len(history)
        variance = sum((value - mean) ** 2 for value in history) / len(history)
        scale = max(math.sqrt(variance), abs(mean) * 0.01, 0.01)
        return max(0.0, min(1.0, abs(latest - forecast) / (4 * scale)))


class ChronosBoltAdapter:
    """Lazy optional forecasting adapter; never downloads weights by default."""

    name = "amazon/chronos-bolt-tiny"

    def __init__(self) -> None:
        self._pipeline = None

    @property
    def enabled(self) -> bool:
        return os.getenv("AAPAD_EDGE_CHRONOS_ENABLED", "false").lower() in {"1", "true", "yes", "on"}

    def _load(self):
        if not self.enabled:
            raise RuntimeError("Chronos is disabled")
        if self._pipeline is not None:
            return self._pipeline
        try:
            import torch
            from chronos import BaseChronosPipeline
        except ImportError as exc:
            raise RuntimeError("Install requirements-chronos.txt to enable Chronos") from exc
        allow_download = os.getenv("AAPAD_EDGE_CHRONOS_ALLOW_DOWNLOAD", "false").lower() in {
            "1", "true", "yes", "on"
        }
        self._pipeline = BaseChronosPipeline.from_pretrained(
            self.name,
            device_map="cpu",
            torch_dtype=torch.float32,
            local_files_only=not allow_download,
        )
        return self._pipeline

    def anomaly_score(self, values: list[float]) -> float:
        if len(values) < 8:
            return 0.0
        import torch

        pipeline = self._load()
        forecast = pipeline.predict(
            context=torch.tensor(values[:-1], dtype=torch.float32),
            prediction_length=1,
        )
        median = float(forecast[0, forecast.shape[1] // 2, 0])
        spread = max(float(forecast[0, -1, 0] - forecast[0, 0, 0]), 0.01)
        return max(0.0, min(1.0, abs(values[-1] - median) / (2 * spread)))
