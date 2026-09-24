from __future__ import annotations

import math
from datetime import datetime, timezone
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from . import EDGE_SCHEMA_VERSION
from .catalog import profile_definition, property_definition, region_definition


def _camel(name: str) -> str:
    first, *rest = name.split("_")
    return first + "".join(item[:1].upper() + item[1:] for item in rest)


class EdgeModel(BaseModel):
    model_config = ConfigDict(alias_generator=_camel, populate_by_name=True, extra="forbid")


class EdgeLocation(EdgeModel):
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
    elevation_m: float | None = Field(default=None, ge=-500, le=9000)

    @field_validator("latitude", "longitude", "elevation_m")
    @classmethod
    def finite_location(cls, value: float | None) -> float | None:
        if value is not None and not math.isfinite(value):
            raise ValueError("Location values must be finite")
        return value


class DeviceHealth(EdgeModel):
    battery_pct: float = Field(ge=0, le=100)
    signal_quality_pct: float = Field(ge=0, le=100)

    @field_validator("battery_pct", "signal_quality_pct")
    @classmethod
    def finite_health(cls, value: float) -> float:
        if not math.isfinite(value):
            raise ValueError("Device health values must be finite")
        return value


class SimulationMetadata(EdgeModel):
    scenario_id: str = Field(min_length=2, max_length=100)
    ground_truth_state: Literal["normal", "watch", "warning", "critical", "recovery", "failure"]
    run_id: str = Field(default="", max_length=64)


class TelemetryEnvelope(EdgeModel):
    schema_version: str
    message_id: UUID
    device_id: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]{2,119}$")
    device_type: Literal["river_gauge", "hillslope_station", "coastal_buoy"]
    timestamp: datetime
    sequence_number: int = Field(ge=0, le=9_223_372_036_854_775_807)
    location: EdgeLocation
    measurements: dict[str, float | None] = Field(min_length=1, max_length=32)
    device_health: DeviceHealth
    simulation: SimulationMetadata | None = None

    @field_validator("schema_version")
    @classmethod
    def supported_version(cls, value: str) -> str:
        if value != EDGE_SCHEMA_VERSION:
            raise ValueError(f"Only schemaVersion {EDGE_SCHEMA_VERSION} is supported")
        return value

    @field_validator("timestamp")
    @classmethod
    def utc_timestamp(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("timestamp must include a timezone")
        return value.astimezone(timezone.utc)

    @field_validator("measurements")
    @classmethod
    def known_finite_measurements(cls, values: dict[str, float | None]) -> dict[str, float | None]:
        for name, value in values.items():
            definition = property_definition(name)
            if definition is None:
                raise ValueError(f"Unsupported observed property: {name}")
            if value is None:
                continue
            if isinstance(value, bool) or not math.isfinite(float(value)):
                raise ValueError(f"{name} must be a finite number")
            if float(value) < definition["min"] or float(value) > definition["max"]:
                raise ValueError(
                    f"{name} must be between {definition['min']} and {definition['max']} {definition['unit']}"
                )
        return values


class DeviceCreate(EdgeModel):
    device_id: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]{2,119}$")
    name: str = Field(min_length=2, max_length=160)
    device_type: Literal["river_gauge", "hillslope_station", "coastal_buoy"]
    installed_purposes: list[Literal["flood", "landslide", "tsunami"]] = Field(min_length=1)
    capabilities: list[str] = Field(min_length=1)
    location: EdgeLocation
    region_id: str = Field(min_length=2, max_length=80)
    expected_interval_seconds: int = Field(default=60, ge=5, le=86400)
    simulation_only: bool = True

    @model_validator(mode="after")
    def validate_registry_contract(self) -> "DeviceCreate":
        profile = profile_definition(self.device_type)
        if profile is None:
            raise ValueError("Unknown device type")
        allowed = set(profile["capabilities"])
        unsupported = sorted(set(self.capabilities) - allowed)
        if unsupported:
            raise ValueError(f"Capabilities do not match {self.device_type}: {unsupported}")
        if not set(self.installed_purposes).issubset(set(profile["purposes"])):
            raise ValueError("Installed purpose does not match the selected device profile")
        if region_definition(self.region_id) is None:
            raise ValueError("Unknown configured region")
        return self


class SimulationCreate(EdgeModel):
    scenario: str = "flood-gradual-001"
    number_of_devices: int = Field(default=9, ge=1, le=50)
    seed: int = Field(default=20260902, ge=0, le=2_147_483_647)
    region: str = "visakhapatnam"
    speed_multiplier: float = Field(default=30.0, ge=0.25, le=300)
    timestep_seconds: int = Field(default=60, ge=10, le=3600)

    @model_validator(mode="after")
    def configured_values(self) -> "SimulationCreate":
        from .catalog import scenario_catalog

        if self.scenario not in {item["id"] for item in scenario_catalog()}:
            raise ValueError("Unknown simulation scenario")
        if region_definition(self.region) is None:
            raise ValueError("Unknown simulation region")
        return self


class RiskEventReviewCreate(EdgeModel):
    action: Literal["acknowledge", "promote_to_incident", "dismiss"]
    reviewer_name: str = Field(min_length=2, max_length=120)
    note: str = Field(default="", max_length=600)
    confirm_demo_only: bool = False

    @model_validator(mode="after")
    def require_confirmation(self) -> "RiskEventReviewCreate":
        if self.action == "promote_to_incident" and not self.confirm_demo_only:
            raise ValueError("confirmDemoOnly must be true before promotion")
        return self
