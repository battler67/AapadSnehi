from __future__ import annotations

from ..models import Source
from ..schemas import IncidentCandidate
from ..services.normalizer import infer_severity, parse_datetime, point_from_geojson
from .base import BaseAdapter
from .registry import register_adapter


EONET_TYPES = {
    "wildfires": "wildfire",
    "severeStorms": "storm",
    "floods": "flood",
    "landslides": "landslide",
    "drought": "drought",
    "volcanoes": "volcano",
    "seaLakeIce": "other",
    "earthquakes": "earthquake",
}


@register_adapter("eonet")
class EonetAdapter(BaseAdapter):
    async def fetch(self, source: Source) -> list[IncidentCandidate]:
        payload = await self.get_json(source.endpoint)
        candidates: list[IncidentCandidate] = []
        for event in payload.get("events", [])[:100]:
            geometry = event.get("geometry") or []
            if not geometry:
                continue
            latest = geometry[-1]
            point = point_from_geojson(latest)
            if point is None:
                continue
            latitude, longitude = point
            category_id = str(((event.get("categories") or [{}])[0]).get("id") or "")
            disaster_type = EONET_TYPES.get(category_id, "other")
            title = str(event.get("title") or "NASA EONET event")
            source_links = event.get("sources") or []
            link = str((source_links[0] if source_links else {}).get("url") or event.get("link") or "")
            magnitude_value = latest.get("magnitudeValue")
            supplied = None
            if isinstance(magnitude_value, (int, float)):
                supplied = 5 if magnitude_value >= 7 else 4 if magnitude_value >= 5 else 3
            candidates.append(
                IncidentCandidate(
                    external_id=str(event.get("id") or title),
                    title=title[:240],
                    description=str(event.get("description") or "Curated natural event from NASA EONET.")[:1800],
                    disaster_type=disaster_type,
                    severity=infer_severity(title, disaster_type, supplied),
                    latitude=latitude,
                    longitude=longitude,
                    location_name="NASA EONET event geometry",
                    occurred_at=parse_datetime(latest.get("date")),
                    source_kind="official",
                    verification_status="official",
                    source_url=link,
                    affected_estimate=0,
                    needs=["verification"],
                )
            )
        return candidates
