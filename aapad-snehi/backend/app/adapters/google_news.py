from __future__ import annotations

import html
import re
import xml.etree.ElementTree as ET
from urllib.parse import urlparse

from ..models import Source
from ..schemas import IncidentCandidate
from ..services.normalizer import normalize_article
from .base import AdapterConfigurationError, AdapterError, BaseAdapter
from .registry import register_adapter


GOOGLE_NEWS_RESULT_LIMIT = 5


def validate_google_news_url(url: str) -> str:
    parsed = urlparse(url)
    if (
        parsed.scheme != "https"
        or parsed.hostname != "news.google.com"
        or not (parsed.path == "/rss" or parsed.path.startswith("/rss/"))
        or parsed.port not in (None, 443)
        or parsed.fragment
        or parsed.username
        or parsed.password
    ):
        raise AdapterConfigurationError(
            "Google News feeds must use a plain https://news.google.com/rss URL"
        )
    return url


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1].lower()


def _child_value(element: ET.Element, *names: str) -> str:
    wanted = {name.lower() for name in names}
    for child in element:
        if _local_name(child.tag) not in wanted:
            continue
        value = child.text or child.attrib.get("href") or ""
        if value.strip():
            return value.strip()
    return ""


def _plain_text(value: str) -> str:
    without_markup = re.sub(r"<[^>]+>", " ", html.unescape(value))
    return re.sub(r"\s+", " ", without_markup).strip()


@register_adapter("google_news")
class GoogleNewsRssAdapter(BaseAdapter):
    snapshot_mode = True

    async def fetch(self, source: Source) -> list[IncidentCandidate]:
        endpoint = validate_google_news_url(source.endpoint)
        body, _ = await self.get_text(endpoint)
        try:
            root = ET.fromstring(body)
        except ET.ParseError as exc:
            raise AdapterError("Google News returned invalid RSS XML") from exc

        entries = [
            element
            for element in root.iter()
            if _local_name(element.tag) in {"item", "entry"}
        ]
        candidates: list[IncidentCandidate] = []
        seen_urls: set[str] = set()
        for entry in entries:
            url = _child_value(entry, "link")
            if not url or url in seen_urls:
                continue
            seen_urls.add(url)
            candidate = normalize_article(
                title=_plain_text(_child_value(entry, "title")) or "Google News result",
                description=_plain_text(
                    _child_value(entry, "description", "summary", "content")
                ),
                url=url,
                published_at=_child_value(entry, "pubDate", "published", "updated"),
                source_kind="news",
                external_id=_child_value(entry, "guid", "id"),
                verification_status="unverified",
            )
            if candidate:
                candidates.append(candidate)
            if len(candidates) == GOOGLE_NEWS_RESULT_LIMIT:
                break
        return candidates
