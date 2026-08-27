from __future__ import annotations

import asyncio
import hashlib
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import ClassVar
from urllib.parse import parse_qs, urlparse

import httpx

from ..models import Source
from ..schemas import IncidentCandidate
from ..services.normalizer import (
    classify_hazard,
    estimate_affected,
    infer_severity,
    needs_for_hazard,
    parse_datetime,
    resolve_location,
)
from .base import AdapterConfigurationError, AdapterError, BaseAdapter
from .registry import register_adapter


SACHET_HOST = "sachet.ndma.gov.in"
SACHET_FEED_PATH = "/cap_public_website/rss/rss_india.xml"
SACHET_CAP_PATH = "/cap_public_website/FetchXMLFile"
SACHET_POLYGON_PATH = "/cap_public_website/FetchPolygonXMLFile"
SACHET_IDENTIFIER = re.compile(r"[A-Za-z0-9_.:-]{1,180}")
MAX_FEED_ITEMS = 200
MAX_CONCURRENT_CAP_REQUESTS = 8
MAX_ETAG_CACHE_ENTRIES = 512
RSS_FALLBACK_MAX_AGE = timedelta(days=7)
INDIA_LOCATION = (22.5937, 78.9629, "India")
GENERIC_AREA_NAMES = {"some parts", "your area", "some places", "isolated places"}

CAP_CATEGORY_NEEDS: dict[str, tuple[str, ...]] = {
    "cbrne": ("medical", "rescue"),
    "env": ("water", "medical"),
    "fire": ("rescue", "medical"),
    "geo": ("transport", "rescue"),
    "health": ("medical",),
    "infra": ("transport", "shelter"),
    "met": ("shelter", "transport"),
    "rescue": ("rescue", "medical"),
    "safety": ("medical", "rescue"),
    "transport": ("transport", "rescue"),
}


@dataclass(frozen=True)
class _CachedXml:
    etag: str
    body: str


def _plain_https_url(url: str) -> tuple[str, str]:
    parsed = urlparse(url)
    try:
        port = parsed.port
    except ValueError as exc:
        raise AdapterConfigurationError("SACHET endpoint contained an invalid port") from exc
    if (
        parsed.scheme != "https"
        or parsed.hostname != SACHET_HOST
        or parsed.username
        or parsed.password
        or port not in (None, 443)
        or parsed.fragment
    ):
        raise AdapterConfigurationError("SACHET endpoints must use the exact public HTTPS host")
    return parsed.path, parsed.query


def validate_sachet_feed_url(url: str) -> str:
    path, query = _plain_https_url(url)
    if path != SACHET_FEED_PATH or query:
        raise AdapterConfigurationError(
            "The SACHET source must be the official all-India rss_india.xml feed"
        )
    return url


def _validate_sachet_linked_url(url: str, expected_path: str, label: str) -> str:
    path, query = _plain_https_url(url)
    values = parse_qs(query, keep_blank_values=True, strict_parsing=True)
    identifiers = values.get("identifier", [])
    if (
        path != expected_path
        or set(values) != {"identifier"}
        or len(identifiers) != 1
        or not SACHET_IDENTIFIER.fullmatch(identifiers[0])
    ):
        raise AdapterConfigurationError(f"SACHET contained an invalid linked {label} URL")
    return url


def validate_sachet_cap_url(url: str) -> str:
    return _validate_sachet_linked_url(url, SACHET_CAP_PATH, "CAP")


def validate_sachet_polygon_url(url: str) -> str:
    return _validate_sachet_linked_url(url, SACHET_POLYGON_PATH, "polygon")


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1].lower()


def _direct_children(element: ET.Element, name: str) -> list[ET.Element]:
    wanted = name.lower()
    return [child for child in element if _local_name(child.tag) == wanted]


def _direct_text(element: ET.Element, name: str) -> str:
    children = _direct_children(element, name)
    if not children:
        return ""
    return (children[0].text or "").strip()


def _coordinates_from_text(raw: str) -> tuple[float, float] | None:
    values = re.split(r"[\s,]+", raw.strip())
    if len(values) < 2:
        return None
    try:
        latitude, longitude = float(values[0]), float(values[1])
    except ValueError:
        return None
    if -90 <= latitude <= 90 and -180 <= longitude <= 180:
        return latitude, longitude
    return None


def _centroid_from_info(info: ET.Element) -> tuple[float, float] | None:
    points: list[tuple[float, float]] = []
    for area in _direct_children(info, "area"):
        for point in _direct_children(area, "point"):
            parsed = _coordinates_from_text(point.text or "")
            if parsed:
                points.append(parsed)
        for circle in _direct_children(area, "circle"):
            parsed = _coordinates_from_text(circle.text or "")
            if parsed:
                points.append(parsed)
        for polygon in _direct_children(area, "polygon"):
            for raw_pair in (polygon.text or "").split():
                parsed = _coordinates_from_text(raw_pair)
                if parsed:
                    points.append(parsed)
    if not points:
        return None
    return (
        sum(point[0] for point in points) / len(points),
        sum(point[1] for point in points) / len(points),
    )


def _centroid_from_polygon_document(body: str) -> tuple[float, float] | None:
    try:
        root = ET.fromstring(body)
    except ET.ParseError as exc:
        raise AdapterError("SACHET returned invalid polygon XML") from exc
    points: list[tuple[float, float]] = []
    for element in root.iter():
        name = _local_name(element.tag)
        raw = (element.text or "").strip()
        if not raw:
            continue
        if name in {"point", "circle"}:
            parsed = _coordinates_from_text(raw)
            if parsed:
                points.append(parsed)
        elif name == "polygon":
            points.extend(
                parsed
                for pair in raw.split()
                if (parsed := _coordinates_from_text(pair)) is not None
            )
        elif name == "coordinates":
            for pair in raw.split():
                values = pair.split(",")
                if len(values) < 2:
                    continue
                try:
                    longitude, latitude = float(values[0]), float(values[1])
                except ValueError:
                    continue
                if -90 <= latitude <= 90 and -180 <= longitude <= 180:
                    points.append((latitude, longitude))
    if not points:
        return None
    return (
        sum(point[0] for point in points) / len(points),
        sum(point[1] for point in points) / len(points),
    )


def _area_context(info: ET.Element) -> tuple[str, str]:
    area_names: list[str] = []
    geocode_parts: list[str] = []
    for area in _direct_children(info, "area"):
        area_name = _direct_text(area, "areaDesc")
        if area_name:
            area_names.append(area_name)
        for geocode in _direct_children(area, "geocode"):
            name = _direct_text(geocode, "valueName")
            value = _direct_text(geocode, "value")
            geocode_parts.extend(part for part in (name, value) if part)
    return (
        "; ".join(dict.fromkeys(area_names)),
        " ".join(dict.fromkeys(geocode_parts)),
    )


def _polygon_url(info: ET.Element) -> str:
    for parameter in _direct_children(info, "parameter"):
        if _direct_text(parameter, "valueName").strip().lower() == "polygon url":
            return _direct_text(parameter, "value")
    return ""


def _strict_datetime(raw: str) -> datetime | None:
    if not raw:
        return None
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _preferred_info(root: ET.Element) -> ET.Element | None:
    infos = _direct_children(root, "info")
    if not infos:
        return None
    return next(
        (
            info
            for info in infos
            if _direct_text(info, "language").lower().startswith("en")
        ),
        infos[0],
    )


def _cap_hazard(event: str, combined: str, category: str) -> str | None:
    hazard = classify_hazard(combined)
    if hazard != "other":
        return hazard
    event_slug = re.sub(
        r"(?:^|_)(?:alert|warning|watch|advisory|notification)(?:_|$)",
        "_",
        re.sub(r"[^a-z0-9]+", "_", event.lower()).strip("_"),
    ).strip("_")
    if event_slug:
        return event_slug[:40]
    if category.lower() == "met":
        return "storm"
    return None


def _cap_needs(combined: str, hazard: str, category: str) -> list[str]:
    needs = needs_for_hazard(combined, hazard)
    return needs or list(CAP_CATEGORY_NEEDS.get(category.lower(), ("verification",)))


@register_adapter("sachet")
class SachetCapRssAdapter(BaseAdapter):
    snapshot_mode = True
    _etag_cache: ClassVar[dict[str, _CachedXml]] = {}

    def __init__(self) -> None:
        self._client: httpx.AsyncClient | None = None
        self._polygon_probe_lock = asyncio.Lock()
        self._polygon_access_confirmed = False
        self._polygon_access_blocked = False

    async def fetch(self, source: Source) -> list[IncidentCandidate]:
        endpoint = validate_sachet_feed_url(source.endpoint)
        self._polygon_access_confirmed = False
        self._polygon_access_blocked = False
        async with self.create_http_client() as client:
            self._client = client
            try:
                feed_body = await self._get_cached_xml(endpoint)
                try:
                    root = ET.fromstring(feed_body)
                except ET.ParseError as exc:
                    raise AdapterError("SACHET returned invalid RSS XML") from exc

                items = [
                    element
                    for element in root.iter()
                    if _local_name(element.tag) == "item"
                ]
                unique_items: list[ET.Element] = []
                seen: set[str] = set()
                for item in items:
                    identity = (
                        _direct_text(item, "guid")
                        or _direct_text(item, "link")
                        or _direct_text(item, "title")
                    )
                    if not identity or identity in seen:
                        continue
                    seen.add(identity)
                    unique_items.append(item)
                    if len(unique_items) >= MAX_FEED_ITEMS:
                        break

                semaphore = asyncio.Semaphore(MAX_CONCURRENT_CAP_REQUESTS)

                async def bounded(item: ET.Element) -> IncidentCandidate | None:
                    async with semaphore:
                        return await self._process_item(item, source)

                results = await asyncio.gather(*(bounded(item) for item in unique_items))
                return [candidate for candidate in results if candidate is not None]
            finally:
                self._client = None

    async def _process_item(
        self,
        item: ET.Element,
        source: Source,
    ) -> IncidentCandidate | None:
        detail_url = _direct_text(item, "link")
        if not detail_url:
            return self._from_rss(item, source)
        try:
            validate_sachet_cap_url(detail_url)
        except (AdapterConfigurationError, ValueError):
            return None
        try:
            cap_body = await self._get_cached_xml(detail_url)
            return await self._from_cap(cap_body, item, detail_url)
        except (AdapterError, httpx.HTTPError, UnicodeError, ValueError):
            return self._from_rss(item, source)

    async def _get_cached_xml(self, url: str) -> str:
        cached = self._etag_cache.get(url)
        headers = {"If-None-Match": cached.etag} if cached and cached.etag else None
        response = await self.request_with_metadata(
            "GET",
            url,
            headers=headers,
            allow_not_modified=True,
            client=self._client,
        )
        if response.status_code == 304:
            if not cached:
                raise AdapterError("SACHET returned 304 before any XML was cached")
            return cached.body
        body = response.body.decode("utf-8", errors="replace")
        etag = next(
            (value for key, value in response.headers.items() if key.lower() == "etag"),
            "",
        )
        if etag:
            if len(self._etag_cache) >= MAX_ETAG_CACHE_ENTRIES:
                self._etag_cache.pop(next(iter(self._etag_cache)))
            self._etag_cache[url] = _CachedXml(etag=etag, body=body)
        return body

    async def _from_cap(
        self,
        body: str,
        rss_item: ET.Element,
        detail_url: str,
    ) -> IncidentCandidate | None:
        try:
            root = ET.fromstring(body)
        except ET.ParseError as exc:
            raise AdapterError("SACHET returned invalid CAP XML") from exc
        if _local_name(root.tag) != "alert":
            raise AdapterError("SACHET linked document was not a CAP alert")
        if _direct_text(root, "status").lower() != "actual":
            return None
        scope = _direct_text(root, "scope").lower()
        if scope and scope != "public":
            return None
        if _direct_text(root, "msgType").lower() == "cancel":
            return None

        info = _preferred_info(root)
        if info is None:
            return None
        expires = _strict_datetime(_direct_text(info, "expires"))
        if expires and expires <= datetime.now(timezone.utc):
            return None

        event = _direct_text(info, "event")
        category = _direct_text(info, "category")
        title = (
            _direct_text(info, "headline")
            or event
            or _direct_text(rss_item, "title")
        )
        description_parts = [
            _direct_text(info, "description"),
            _direct_text(info, "instruction"),
        ]
        description = " ".join(dict.fromkeys(part for part in description_parts if part))
        area_name, geocode_text = _area_context(info)
        sender = _direct_text(root, "sender")
        combined = f"{event}. {title}. {description}. {area_name}. {geocode_text}".strip()
        hazard = _cap_hazard(event, combined, category)
        if not title or hazard is None:
            return None

        coordinates = _centroid_from_info(info)
        polygon_url = _polygon_url(info)
        if coordinates is None and polygon_url:
            try:
                validate_sachet_polygon_url(polygon_url)
            except (AdapterConfigurationError, ValueError):
                polygon_url = ""
            if polygon_url:
                coordinates = await self._fetch_polygon_coordinates(polygon_url)
        structured_location = resolve_location(f"{geocode_text} {area_name}")
        sender_location = resolve_location(re.sub(r"[-_]+", " ", sender))
        headline_location = resolve_location(title)
        resolved = structured_location or sender_location or headline_location
        if coordinates is not None:
            latitude, longitude = coordinates
        elif resolved:
            latitude, longitude, location_name = resolved
        else:
            latitude, longitude, location_name = INDIA_LOCATION
        if area_name and area_name.strip().lower() not in GENERIC_AREA_NAMES:
            location_name = area_name
        elif structured_location:
            location_name = structured_location[2]
        elif sender_location:
            location_name = sender_location[2]
        elif headline_location:
            location_name = headline_location[2]
        else:
            location_name = INDIA_LOCATION[2]

        severity_levels = {
            "extreme": 5,
            "severe": 4,
            "moderate": 3,
            "minor": 2,
            "unknown": 2,
        }
        supplied_severity = severity_levels.get(_direct_text(info, "severity").lower())
        identifier = _direct_text(root, "identifier") or _direct_text(rss_item, "guid")
        stable_id = identifier or hashlib.sha256(detail_url.encode()).hexdigest()[:24]
        occurred_at = parse_datetime(
            _direct_text(root, "sent")
            or _direct_text(info, "effective")
            or _direct_text(info, "onset")
            or _direct_text(rss_item, "pubDate")
        )
        return IncidentCandidate(
            external_id=stable_id,
            title=title[:240],
            description=description[:1800],
            disaster_type=hazard,
            severity=infer_severity(combined, hazard, supplied_severity),
            latitude=latitude,
            longitude=longitude,
            location_name=location_name[:180],
            occurred_at=occurred_at,
            source_kind="official",
            verification_status="official",
            source_url=detail_url,
            affected_estimate=estimate_affected(combined),
            needs=_cap_needs(combined, hazard, category),
        )

    async def _fetch_polygon_coordinates(
        self,
        polygon_url: str,
    ) -> tuple[float, float] | None:
        if self._polygon_access_blocked:
            return None
        if not self._polygon_access_confirmed:
            async with self._polygon_probe_lock:
                if self._polygon_access_blocked:
                    return None
                if not self._polygon_access_confirmed:
                    return await self._request_polygon_coordinates(polygon_url, probe=True)
        return await self._request_polygon_coordinates(polygon_url, probe=False)

    async def _request_polygon_coordinates(
        self,
        polygon_url: str,
        *,
        probe: bool,
    ) -> tuple[float, float] | None:
        try:
            body = await self._get_cached_xml(polygon_url)
        except httpx.HTTPStatusError as exc:
            if probe and exc.response.status_code in {401, 403, 404}:
                self._polygon_access_blocked = True
            return None
        except (AdapterError, httpx.HTTPError, UnicodeError):
            return None
        self._polygon_access_confirmed = True
        try:
            return _centroid_from_polygon_document(body)
        except AdapterError:
            return None

    def _from_rss(
        self,
        item: ET.Element,
        source: Source,
    ) -> IncidentCandidate | None:
        title = _direct_text(item, "title")
        if not title:
            return None
        occurred_at = parse_datetime(_direct_text(item, "pubDate"))
        now = datetime.now(timezone.utc)
        if occurred_at < now - RSS_FALLBACK_MAX_AGE:
            return None
        category = _direct_text(item, "category")
        hazard = classify_hazard(title)
        if hazard == "other":
            hazard = "storm" if category.lower() == "met" else "official_alert"
        identifier = _direct_text(item, "guid")
        detail_url = _direct_text(item, "link") or source.endpoint
        stable_id = identifier or hashlib.sha256(f"{title}|{detail_url}".encode()).hexdigest()[:24]
        description = (
            f"Official SACHET {category or 'CAP'} alert for India; "
            "linked CAP details were temporarily unavailable."
        )
        resolved = resolve_location(title)
        latitude, longitude, location_name = resolved or INDIA_LOCATION
        return IncidentCandidate(
            external_id=stable_id,
            title=title[:240],
            description=description,
            disaster_type=hazard,
            severity=infer_severity(title, hazard),
            latitude=latitude,
            longitude=longitude,
            location_name=location_name,
            occurred_at=occurred_at,
            source_kind="official",
            verification_status="official",
            source_url=detail_url,
            affected_estimate=estimate_affected(title),
            needs=_cap_needs(title, hazard, category),
        )
