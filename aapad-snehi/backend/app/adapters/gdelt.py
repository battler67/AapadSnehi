from __future__ import annotations

from ..models import Source
from ..schemas import IncidentCandidate
from ..services.normalizer import normalize_article
from .base import BaseAdapter
from .registry import register_adapter


@register_adapter("gdelt")
class GdeltAdapter(BaseAdapter):
    async def fetch(self, source: Source) -> list[IncidentCandidate]:
        payload = await self.get_json(
            source.endpoint,
            params={
                "query": '(flood OR earthquake OR cyclone OR landslide OR wildfire OR "heat wave") India',
                "mode": "artlist",
                "maxrecords": "50",
                "timespan": "7d",
                "sort": "datedesc",
                "format": "json",
            },
        )
        candidates: list[IncidentCandidate] = []
        for article in payload.get("articles", []):
            title = str(article.get("title") or "Disaster-related web result")
            candidate = normalize_article(
                title=title,
                description=f"{article.get('sourcecountry', '')} {article.get('domain', '')}",
                url=str(article.get("url") or ""),
                published_at=article.get("seendate"),
                source_kind="search",
                verification_status="unverified",
            )
            if candidate:
                candidates.append(candidate)
        return candidates
