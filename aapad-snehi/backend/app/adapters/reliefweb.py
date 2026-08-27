from __future__ import annotations

from ..config import settings
from ..models import Source
from ..schemas import IncidentCandidate
from ..services.normalizer import normalize_article
from .base import AdapterConfigurationError, BaseAdapter
from .registry import register_adapter


@register_adapter("reliefweb")
class ReliefWebAdapter(BaseAdapter):
    async def fetch(self, source: Source) -> list[IncidentCandidate]:
        if not settings.reliefweb_appname:
            raise AdapterConfigurationError(
                "ReliefWeb live access requires an approved AAPAD_RELIEFWEB_APPNAME"
            )
        payload = await self.get_json(
            source.endpoint,
            params={
                "appname": settings.reliefweb_appname,
                "limit": "40",
                "preset": "latest",
                "profile": "full",
                "query[value]": "flood OR earthquake OR cyclone OR landslide OR wildfire OR heatwave",
            },
        )
        candidates: list[IncidentCandidate] = []
        for item in payload.get("data", []):
            fields = item.get("fields") or {}
            body = str(fields.get("body") or fields.get("body-html") or "")
            countries = ", ".join(
                str(country.get("name") or "") for country in fields.get("country", [])
            )
            candidate = normalize_article(
                title=str(fields.get("title") or "ReliefWeb report"),
                description=f"{countries}. {body}"[:1800],
                url=str(fields.get("url") or fields.get("url_alias") or ""),
                published_at=(fields.get("date") or {}).get("created"),
                source_kind="news",
                external_id=str(item.get("id") or ""),
                verification_status="corroborated",
            )
            if candidate:
                candidates.append(candidate)
        return candidates
