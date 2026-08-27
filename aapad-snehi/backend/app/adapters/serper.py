from __future__ import annotations

from urllib.parse import urlparse

from ..config import settings
from ..models import Source
from ..schemas import IncidentCandidate
from ..services.normalizer import normalize_article
from .base import AdapterConfigurationError, BaseAdapter
from .registry import register_adapter


SERPER_SEARCH_QUERY = (
    'India (flood OR earthquake OR cyclone OR landslide OR wildfire OR "forest fire" '
    'OR heatwave OR "heat wave" OR drought OR "building collapse" OR "dam failure")'
)
SERPER_RESULT_LIMIT = 5


def validate_serper_url(url: str) -> str:
    parsed = urlparse(url)
    if (
        parsed.scheme != "https"
        or parsed.hostname != "google.serper.dev"
        or parsed.path.rstrip("/") != "/search"
        or parsed.port not in (None, 443)
        or parsed.query
        or parsed.fragment
        or parsed.username
        or parsed.password
    ):
        raise AdapterConfigurationError(
            "Serper searches must use the reviewed https://google.serper.dev/search endpoint"
        )
    return url


def _result_position(item: dict) -> int:
    try:
        return int(item.get("position") or 10_000)
    except (TypeError, ValueError):
        return 10_000


@register_adapter("serper")
class SerperSearchAdapter(BaseAdapter):
    snapshot_mode = True

    async def fetch(self, source: Source) -> list[IncidentCandidate]:
        if not settings.serper_api_key:
            raise AdapterConfigurationError(
                "Serper live access requires AAPAD_SERPER_API_KEY"
            )
        endpoint = validate_serper_url(source.endpoint)
        payload = await self.post_json(
            endpoint,
            headers={
                "X-API-KEY": settings.serper_api_key,
                "Content-Type": "application/json",
            },
            json_payload={
                "q": SERPER_SEARCH_QUERY,
                "gl": "in",
                "hl": "en",
                "num": 20,
                "tbs": "qdr:w",
            },
        )

        results = payload.get("organic", [])
        if not isinstance(results, list):
            return []
        ordered = sorted(
            (item for item in results if isinstance(item, dict)),
            key=_result_position,
        )
        candidates: list[IncidentCandidate] = []
        seen_urls: set[str] = set()
        for item in ordered:
            url = str(item.get("link") or "").strip()
            if not url or url in seen_urls:
                continue
            seen_urls.add(url)
            candidate = normalize_article(
                title=str(item.get("title") or "Disaster-related web result"),
                description=str(item.get("snippet") or ""),
                url=url,
                published_at=item.get("date"),
                source_kind="search",
                verification_status="unverified",
            )
            if candidate:
                candidates.append(candidate)
            if len(candidates) == SERPER_RESULT_LIMIT:
                break
        return candidates
