from __future__ import annotations

from datetime import datetime, timedelta, timezone

from ..models import Source
from ..schemas import IncidentCandidate
from .base import BaseAdapter
from .registry import register_adapter


@register_adapter("seed")
class SeedAdapter(BaseAdapter):
    async def fetch(self, source: Source) -> list[IncidentCandidate]:
        now = datetime.now(timezone.utc)
        return [
            IncidentCandidate(
                external_id="assam-flood",
                title="Assam flood relief corridor",
                description="Demo validation record for food, shelter and medical response.",
                disaster_type="flood",
                severity=5,
                latitude=26.2006,
                longitude=92.9376,
                location_name="Nagaon, Assam",
                occurred_at=now - timedelta(hours=2),
                source_kind="demo",
                verification_status="official",
                affected_estimate=18500,
                needs=["food", "shelter", "medical"],
            ),
            IncidentCandidate(
                external_id="uttarkashi-slide",
                title="Landslide blocks Uttarkashi access",
                description="Demo validation record for rescue, medical and transport support.",
                disaster_type="landslide",
                severity=4,
                latitude=30.7268,
                longitude=78.4354,
                location_name="Uttarkashi, Uttarakhand",
                occurred_at=now - timedelta(hours=7),
                source_kind="demo",
                verification_status="official",
                affected_estimate=3400,
                needs=["rescue", "medical", "transport"],
            ),
            IncidentCandidate(
                external_id="odisha-cyclone",
                title="Coastal cyclone shelter readiness",
                description="Demo validation record for shelter and transport support.",
                disaster_type="cyclone",
                severity=4,
                latitude=19.8135,
                longitude=85.8312,
                location_name="Puri, Odisha",
                occurred_at=now - timedelta(hours=18),
                source_kind="demo",
                verification_status="official",
                affected_estimate=7200,
                needs=["shelter", "transport", "food"],
            ),
        ]
