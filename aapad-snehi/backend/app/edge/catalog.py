from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any


CONFIG_PATH = Path(__file__).resolve().parent / "data" / "edge_config.json"


@lru_cache(maxsize=1)
def edge_config() -> dict[str, Any]:
    payload = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    if payload.get("version") != "edge-demo-config-v1":
        raise RuntimeError("Unsupported edge configuration version")
    return payload


def property_definition(name: str) -> dict[str, Any] | None:
    value = edge_config()["properties"].get(name)
    return value if isinstance(value, dict) else None


def profile_definition(device_type: str) -> dict[str, Any] | None:
    value = edge_config()["profiles"].get(device_type)
    return value if isinstance(value, dict) else None


def scenario_catalog() -> list[dict[str, Any]]:
    return [dict(item) for item in edge_config()["scenarios"]]


def region_definition(region_id: str) -> dict[str, Any] | None:
    value = edge_config()["regions"].get(region_id)
    return value if isinstance(value, dict) else None


def region_catalog() -> list[dict[str, Any]]:
    return [{"id": region_id, **dict(value)} for region_id, value in edge_config()["regions"].items()]
