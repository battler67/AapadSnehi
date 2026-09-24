from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


def _camel(name: str) -> str:
    first, *rest = name.split("_")
    return first + "".join(item[:1].upper() + item[1:] for item in rest)


class MLModel(BaseModel):
    model_config = ConfigDict(
        alias_generator=_camel,
        populate_by_name=True,
        extra="forbid",
    )


class PredictionRequest(MLModel):
    model_id: str = Field(min_length=2, max_length=80, pattern=r"^[a-z0-9-]+$")
    source: Literal[
        "manual",
        "synthetic",
        "weather_api",
        "iot_sensor",
        "edge_device",
        "official_disaster_api",
    ] = "manual"
    features: dict[str, Any]
    units_confirmed: bool = False
    prediction_time: datetime | None = None
    latest_input_available_at: datetime | None = None
    latest_observation_time: datetime | None = None

    @field_validator(
        "prediction_time",
        "latest_input_available_at",
        "latest_observation_time",
    )
    @classmethod
    def timezone_required(cls, value: datetime | None) -> datetime | None:
        if value is not None and (value.tzinfo is None or value.utcoffset() is None):
            raise ValueError("Timestamps must include a timezone")
        return value
