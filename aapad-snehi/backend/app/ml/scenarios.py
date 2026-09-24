from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

import numpy as np


FLOOD_SCENARIOS = {
    "low": {
        "label": "Low-flow dry-day demonstration",
        "description": "A supported catchment row with little recent rain and stable flow.",
        "changes": {
            "prcp(mm/day)": 0.0,
            "rain_sum_3": 0.0,
            "rain_sum_7": 2.0,
            "rain_sum_14": 8.0,
            "rain_sum_30": 20.0,
            "discharge": 42.71,
            "discharge_lag_1": 42.71,
            "discharge_lag_2": 44.0,
            "discharge_lag_3": 45.0,
            "discharge_lag_7": 48.0,
            "discharge_lag_14": 52.0,
            "discharge_lag_30": 44.14,
            "discharge_trend_3": -2.29,
            "discharge_trend_7": -5.29,
        },
    },
    "medium": {
        "label": "Elevated rain and flow demonstration",
        "description": "Synthetic recent rainfall and increasing discharge on the same supported catchment.",
        "changes": {
            "prcp(mm/day)": 28.0,
            "rain_sum_3": 62.0,
            "rain_sum_7": 118.0,
            "rain_sum_14": 172.0,
            "rain_sum_30": 260.0,
            "discharge": 210.0,
            "discharge_lag_1": 210.0,
            "discharge_lag_2": 180.0,
            "discharge_lag_3": 150.0,
            "discharge_lag_7": 95.0,
            "discharge_lag_14": 72.0,
            "discharge_lag_30": 55.0,
            "discharge_trend_3": 80.0,
            "discharge_trend_7": 125.0,
        },
    },
    "high": {
        "label": "High-flow stress demonstration",
        "description": "Synthetic heavy rainfall and rapidly rising discharge; not a recorded event.",
        "changes": {
            "prcp(mm/day)": 110.0,
            "rain_sum_3": 240.0,
            "rain_sum_7": 420.0,
            "rain_sum_14": 610.0,
            "rain_sum_30": 820.0,
            "discharge": 920.0,
            "discharge_lag_1": 920.0,
            "discharge_lag_2": 700.0,
            "discharge_lag_3": 520.0,
            "discharge_lag_7": 260.0,
            "discharge_lag_14": 140.0,
            "discharge_lag_30": 80.0,
            "discharge_trend_3": 520.0,
            "discharge_trend_7": 700.0,
        },
    },
}


WILDFIRE_SCENARIOS = {
    "low": {
        "label": "Cooler, wetter existing-fire scene",
        "description": "Synthetic aligned grid with a small known active-fire cluster.",
        "values": {"pdsi": 1.5, "pr": 8.0, "sph": 0.009, "tmmn": 276.0, "tmmx": 291.0, "vs": 2.0, "erc": 22.0},
        "radius": 1,
    },
    "medium": {
        "label": "Dry, windy existing-fire scene",
        "description": "Synthetic aligned grid with moderate fire-weather conditions.",
        "values": {"pdsi": 4.0, "pr": 2.0, "sph": 0.006, "tmmn": 286.0, "tmmx": 304.0, "vs": 5.5, "erc": 58.0},
        "radius": 2,
    },
    "high": {
        "label": "Hot, dry existing-fire stress scene",
        "description": "Synthetic aligned grid near documented clipping limits; not a real forecast.",
        "values": {"pdsi": 6.5, "pr": 0.0, "sph": 0.0035, "tmmn": 295.0, "tmmx": 313.0, "vs": 9.0, "erc": 96.0},
        "radius": 3,
    },
}


def scenario_catalog(model_kind: str) -> list[dict[str, str]]:
    source = WILDFIRE_SCENARIOS if model_kind == "wildfire" else FLOOD_SCENARIOS
    return [
        {"id": key, "label": value["label"], "description": value["description"]}
        for key, value in source.items()
    ]


def flood_scenario(root: Path, scenario_id: str) -> dict[str, Any]:
    definition = FLOOD_SCENARIOS.get(scenario_id)
    if definition is None:
        raise KeyError("Unknown synthetic scenario")
    sample_path = root / "artifacts" / "handoff" / "random_forest_input.json"
    payload = json.loads(sample_path.read_text(encoding="utf-8"))
    row = copy.deepcopy(payload["rows"][0])
    row.update(definition["changes"])
    return {
        "source": "synthetic",
        "scenarioId": scenario_id,
        "synthetic": True,
        "features": {"row": row},
        "unitsConfirmed": True,
        "notes": [
            "Synthetic dynamic values with static attributes retained from supported catchment 03005.",
            "This scenario is not a recorded event and has no expected ground-truth outcome.",
        ],
    }
def wildfire_scenario(scenario_id: str) -> dict[str, Any]:
    definition = WILDFIRE_SCENARIOS.get(scenario_id)
    if definition is None:
        raise KeyError("Unknown synthetic scenario")
    size = 64
    yy, xx = np.mgrid[0:size, 0:size]
    elevation = 500.0 + yy * 8.0 + xx * 2.0
    channels: dict[str, np.ndarray] = {
        "elevation": elevation,
        "pdsi": np.full((size, size), definition["values"]["pdsi"]),
        "NDVI": np.full((size, size), 5158.0),
        "pr": np.full((size, size), definition["values"]["pr"]),
        "sph": np.full((size, size), definition["values"]["sph"]),
        "th": np.full((size, size), 225.0),
        "tmmn": np.full((size, size), definition["values"]["tmmn"]),
        "tmmx": np.full((size, size), definition["values"]["tmmx"]),
        "vs": np.full((size, size), definition["values"]["vs"]),
        "erc": np.full((size, size), definition["values"]["erc"]),
        "population": np.full((size, size), 26.0),
        "PrevFireMask": np.zeros((size, size)),
    }
    radius = int(definition["radius"])
    centre = size // 2
    channels["PrevFireMask"][
        centre - radius : centre + radius + 1,
        centre - radius : centre + radius + 1,
    ] = 1.0
    return {
        "source": "synthetic",
        "scenarioId": scenario_id,
        "synthetic": True,
        "features": {"channels": {key: value.tolist() for key, value in channels.items()}},
        "unitsConfirmed": True,
        "notes": [
            "Synthetic aligned 64x64 environmental grids with an explicit existing-fire mask.",
            "The grid has no coordinates or authoritative timestamp and is not a real fire forecast.",
        ],
    }
# End of deterministic demo-scenario generation.
