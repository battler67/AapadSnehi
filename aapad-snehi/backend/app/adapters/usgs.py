from __future__ import annotations

from datetime import datetime, timezone

from ..models import Source
from ..schemas import IncidentCandidate
from .base import BaseAdapter
from .registry import register_adapter


def _severity_for_magnitude(magnitude: float) -> int:
    if magnitude >= 7:
        return 5
    if magnitude >= 6:
        return 4
    if magnitude >= 5:
        return 3
    if magnitude >= 4:
        return 2
    return 1


@register_adapter("usgs")
class UsgsAdapter(BaseAdapter):
    async def fetch(self, source: Source) -> list[IncidentCandidate]:
        payload = await self.get_json(source.endpoint)
        candidates: list[IncidentCandidate] = []
        for feature in payload.get("features", [])[:100]:
            properties = feature.get("properties") or {}
            coordinates = (feature.get("geometry") or {}).get("coordinates") or []
            if len(coordinates) < 2:
                continue
            magnitude = float(properties.get("mag") or 0)
            event_time = datetime.fromtimestamp(
                float(properties.get("time") or 0) / 1000,
                tz=timezone.utc,
            )
            candidates.append(
                IncidentCandidate(
                    external_id=str(feature.get("id") or properties.get("code") or properties.get("time")),
                    title=str(properties.get("title") or properties.get("place") or "Earthquake")[:240],
                    description=f"USGS magnitude {magnitude:.1f} earthquake observation.",
                    disaster_type="earthquake",
                    severity=_severity_for_magnitude(magnitude),
                    latitude=float(coordinates[1]),
                    longitude=float(coordinates[0]),
                    location_name=str(properties.get("place") or "Reported epicentre")[:180],
                    occurred_at=event_time,
                    source_kind="official",
                    verification_status="official",
                    source_url=str(properties.get("url") or ""),
                    affected_estimate=0,
                    needs=["verification", "medical"] if magnitude >= 6 else ["verification"],
                )
            )
        return candidates
