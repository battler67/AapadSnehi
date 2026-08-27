from __future__ import annotations

import hashlib
import ipaddress
import json
import re
import xml.etree.ElementTree as ET
from urllib.parse import urlparse

from ..config import settings
from ..models import Source
from ..schemas import IncidentCandidate
from ..services.normalizer import infer_severity, normalize_article, parse_datetime, point_from_geojson
from .base import AdapterConfigurationError, BaseAdapter
from .registry import register_adapter


def validate_government_url(url: str, allowed_hosts: tuple[str, ...] | None = None) -> str:
    parsed = urlparse(url)
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
        raise AdapterConfigurationError("Government feeds must use a plain HTTPS URL")
    host = parsed.hostname.rstrip(".").lower()
    try:
        address = ipaddress.ip_address(host)
        if address.is_private or address.is_loopback or address.is_link_local or address.is_reserved:
            raise AdapterConfigurationError("Private or local network feed targets are not allowed")
    except ValueError:
        pass
    configured = allowed_hosts or settings.government_hosts
    if not any(host == allowed or host.endswith(f".{allowed}") for allowed in configured):
        raise AdapterConfigurationError(
            f"Host '{host}' is not in AAPAD_GOVERNMENT_HOSTS"
        )
    return url


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1].lower()


def _find_text(element: ET.Element, *names: str) -> str:
    wanted = {name.lower() for name in names}
    for child in element.iter():
        if _local_name(child.tag) in wanted:
            if child.text and child.text.strip():
                return child.text.strip()
            if child.attrib.get("href"):
                return child.attrib["href"].strip()
    return ""


def _coordinates_from_text(raw: str) -> tuple[float, float] | None:
    values = re.split(r"[\s,]+", raw.strip())
    if len(values) < 2:
        return None
    try:
        first, second = float(values[0]), float(values[1])
    except ValueError:
        return None
    if -90 <= first <= 90 and -180 <= second <= 180:
        return first, second
    return None


def _severity_from_cap(value: str, text: str) -> int:
    levels = {"extreme": 5, "severe": 4, "moderate": 3, "minor": 2, "unknown": 1}
    return levels.get(value.lower(), infer_severity(text, "storm"))


@register_adapter("government")
class GovernmentFeedAdapter(BaseAdapter):
    async def fetch(self, source: Source) -> list[IncidentCandidate]:
        endpoint = validate_government_url(source.endpoint)
        body, content_type = await self.get_text(endpoint)
        if "json" in content_type.lower() or body.lstrip().startswith(("{", "[")):
            return self._from_json(body, source)
        return self._from_xml(body, source)

    def _from_json(self, body: str, source: Source) -> list[IncidentCandidate]:
        payload = json.loads(body)
        features = payload.get("features", []) if isinstance(payload, dict) else payload
        candidates: list[IncidentCandidate] = []
        for index, feature in enumerate(features[:100]):
            if not isinstance(feature, dict):
                continue
            properties = feature.get("properties") or feature
            point = point_from_geojson(feature.get("geometry") or {})
            if point is None:
                continue
            latitude, longitude = point
            title = str(properties.get("headline") or properties.get("title") or "Government alert")
            description = str(properties.get("description") or properties.get("instruction") or "")
            candidate = IncidentCandidate(
                external_id=str(properties.get("identifier") or properties.get("id") or f"json-{index}"),
                title=title[:240],
                description=description[:1800],
                disaster_type=str(properties.get("event") or properties.get("type") or "storm").lower(),
                severity=_severity_from_cap(str(properties.get("severity") or ""), f"{title} {description}"),
                latitude=latitude,
                longitude=longitude,
                location_name=str(properties.get("areaDesc") or properties.get("location") or source.authority),
                occurred_at=parse_datetime(properties.get("sent") or properties.get("date")),
                source_kind="official",
                verification_status="official",
                source_url=str(properties.get("web") or source.endpoint),
                affected_estimate=0,
                needs=["verification"],
            )
            candidates.append(candidate)
        return candidates

    def _from_xml(self, body: str, source: Source) -> list[IncidentCandidate]:
        root = ET.fromstring(body)
        entries = [element for element in root.iter() if _local_name(element.tag) in {"item", "entry", "alert"}]
        candidates: list[IncidentCandidate] = []
        for index, entry in enumerate(entries[:100]):
            title = _find_text(entry, "headline", "title", "event") or "Government alert"
            description = _find_text(entry, "description", "summary", "instruction")
            link = _find_text(entry, "link", "web") or source.endpoint
            identifier = _find_text(entry, "identifier", "guid", "id")
            point = _find_text(entry, "point")
            polygon = _find_text(entry, "polygon")
            coordinates = _coordinates_from_text(point)
            if coordinates is None and polygon:
                pairs = [_coordinates_from_text(pair) for pair in polygon.split()]
                valid = [pair for pair in pairs if pair]
                if valid:
                    coordinates = (
                        sum(pair[0] for pair in valid) / len(valid),
                        sum(pair[1] for pair in valid) / len(valid),
                    )
            if coordinates is None:
                article = normalize_article(
                    title=title,
                    description=f"{_find_text(entry, 'areaDesc')} {description}",
                    url=link,
                    published_at=_find_text(entry, "sent", "updated", "pubDate"),
                    source_kind="official",
                    external_id=identifier,
                    verification_status="official",
                )
                if article:
                    candidates.append(article)
                continue
            latitude, longitude = coordinates
            event_name = _find_text(entry, "event")
            disaster_type = re.sub(r"[^a-z]+", "_", event_name.lower()).strip("_") or "storm"
            stable_id = identifier or hashlib.sha256(f"{title}|{link}|{index}".encode()).hexdigest()[:24]
            candidates.append(
                IncidentCandidate(
                    external_id=stable_id,
                    title=title[:240],
                    description=description[:1800],
                    disaster_type=disaster_type,
                    severity=_severity_from_cap(_find_text(entry, "severity"), f"{title} {description}"),
                    latitude=latitude,
                    longitude=longitude,
                    location_name=_find_text(entry, "areaDesc") or source.authority,
                    occurred_at=parse_datetime(_find_text(entry, "sent", "updated", "pubDate")),
                    source_kind="official",
                    verification_status="official",
                    source_url=link,
                    affected_estimate=0,
                    needs=["verification"],
                )
            )
        return candidates
