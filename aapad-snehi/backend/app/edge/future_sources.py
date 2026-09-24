from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


class CorroborationAdapter(Protocol):
    """Future official/satellite evidence contract; never used as edge telemetry."""

    provider: str
    verified_official: bool

    async def corroborate(self, hazard: str, latitude: float, longitude: float, as_of: str) -> list[dict]: ...


@dataclass(frozen=True)
class PlannedAdapter:
    provider: str
    purpose: str
    feature_flag: str
    status: str = "not_implemented"


PLANNED_ADAPTERS = (
    PlannedAdapter("IMD", "weather, rainfall, AWS/ARG and warning corroboration", "AAPAD_EDGE_IMD_ENABLED"),
    PlannedAdapter("CWC", "river-level and flood-forecast corroboration", "AAPAD_EDGE_CWC_ENABLED"),
    PlannedAdapter("NOAA DART", "ocean-bottom-pressure corroboration", "AAPAD_EDGE_DART_ENABLED"),
    PlannedAdapter("Prithvi Sen1Floods11", "asynchronous satellite flood segmentation worker", "AAPAD_EDGE_PRITHVI_ENABLED"),
    PlannedAdapter("Landslide4Sense", "asynchronous satellite landslide corroboration worker", "AAPAD_EDGE_L4S_ENABLED"),
    PlannedAdapter("DeepSlide", "asynchronous satellite landslide corroboration worker", "AAPAD_EDGE_DEEPSLIDE_ENABLED"),
)
