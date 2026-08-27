from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from ..schemas import IncidentCandidate


GAZETTEER: dict[str, tuple[float, float, str]] = {
    "assam": (26.2006, 92.9376, "Assam, India"),
    "guwahati": (26.1445, 91.7362, "Guwahati, Assam"),
    "uttarakhand": (30.0668, 79.0193, "Uttarakhand, India"),
    "uttarkashi": (30.7268, 78.4354, "Uttarkashi, Uttarakhand"),
    "odisha": (20.9517, 85.0985, "Odisha, India"),
    "puri": (19.8135, 85.8312, "Puri, Odisha"),
    "mumbai": (19.0760, 72.8777, "Mumbai, Maharashtra"),
    "maharashtra": (19.7515, 75.7139, "Maharashtra, India"),
    "kerala": (10.8505, 76.2711, "Kerala, India"),
    "kochi": (9.9312, 76.2673, "Kochi, Kerala"),
    "sikkim": (27.5330, 88.5122, "Sikkim, India"),
    "himachal": (31.1048, 77.1734, "Himachal Pradesh, India"),
    "delhi": (28.6139, 77.2090, "Delhi, India"),
    "bihar": (25.0961, 85.3131, "Bihar, India"),
    "patna": (25.5941, 85.1376, "Patna, Bihar"),
    "west bengal": (22.9868, 87.8550, "West Bengal, India"),
    "kolkata": (22.5726, 88.3639, "Kolkata, West Bengal"),
    "chennai": (13.0827, 80.2707, "Chennai, Tamil Nadu"),
    "tamil nadu": (11.1271, 78.6569, "Tamil Nadu, India"),
    "andhra pradesh": (15.9129, 79.7400, "Andhra Pradesh, India"),
    "telangana": (18.1124, 79.0193, "Telangana, India"),
    "arunachal pradesh": (28.2180, 94.7278, "Arunachal Pradesh, India"),
    "meghalaya": (25.4670, 91.3662, "Meghalaya, India"),
    "nagaland": (26.1584, 94.5624, "Nagaland, India"),
    "manipur": (24.6637, 93.9063, "Manipur, India"),
    "mizoram": (23.1645, 92.9376, "Mizoram, India"),
    "tripura": (23.9408, 91.9882, "Tripura, India"),
    "jharkhand": (23.6102, 85.2799, "Jharkhand, India"),
    "chhattisgarh": (21.2787, 81.8661, "Chhattisgarh, India"),
    "madhya pradesh": (22.9734, 78.6569, "Madhya Pradesh, India"),
    "uttar pradesh": (26.8467, 80.9462, "Uttar Pradesh, India"),
    "rajasthan": (27.0238, 74.2179, "Rajasthan, India"),
    "gujarat": (22.2587, 71.1924, "Gujarat, India"),
    "goa": (15.2993, 74.1240, "Goa, India"),
    "karnataka": (15.3173, 75.7139, "Karnataka, India"),
    "punjab": (31.1471, 75.3412, "Punjab, India"),
    "haryana": (29.0588, 76.0856, "Haryana, India"),
    "jammu and kashmir": (33.2778, 75.3412, "Jammu and Kashmir, India"),
    "ladakh": (34.1526, 77.5771, "Ladakh, India"),
    "bengaluru": (12.9716, 77.5946, "Bengaluru, Karnataka"),
    "bangalore": (12.9716, 77.5946, "Bengaluru, Karnataka"),
    "hyderabad": (17.3850, 78.4867, "Hyderabad, Telangana"),
    "ahmedabad": (23.0225, 72.5714, "Ahmedabad, Gujarat"),
    "jaipur": (26.9124, 75.7873, "Jaipur, Rajasthan"),
    "lucknow": (26.8467, 80.9462, "Lucknow, Uttar Pradesh"),
    "bhubaneswar": (20.2961, 85.8245, "Bhubaneswar, Odisha"),
    "india": (22.5937, 78.9629, "India"),
}

DISASTER_KEYWORDS_PATH = (
    Path(__file__).resolve().parents[1] / "data" / "disaster_keywords.json"
)
EXPECTED_DISASTER_KEYWORD_COUNT = 53
ALLOCATION_NEEDS = {"food", "water", "shelter", "medical", "rescue", "transport"}


def _load_disaster_taxonomy() -> tuple[
    dict[str, tuple[str, ...]],
    dict[str, tuple[str, ...]],
]:
    try:
        payload = json.loads(DISASTER_KEYWORDS_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError("Disaster keyword taxonomy could not be loaded") from exc
    if not isinstance(payload, dict) or not isinstance(payload.get("hazards"), list):
        raise RuntimeError("Disaster keyword taxonomy has an invalid shape")
    if payload.get("expected_keyword_count") != EXPECTED_DISASTER_KEYWORD_COUNT:
        raise RuntimeError(
            f"Disaster keyword taxonomy must declare {EXPECTED_DISASTER_KEYWORD_COUNT} keywords"
        )

    keywords_by_hazard: dict[str, tuple[str, ...]] = {}
    needs_by_hazard: dict[str, tuple[str, ...]] = {}
    all_keywords: list[str] = []
    for entry in payload["hazards"]:
        if not isinstance(entry, dict):
            raise RuntimeError("Disaster keyword taxonomy contains an invalid hazard")
        hazard = str(entry.get("type") or "").strip().lower()
        raw_keywords = entry.get("keywords")
        raw_needs = entry.get("default_needs")
        if (
            not hazard
            or hazard in keywords_by_hazard
            or not isinstance(raw_keywords, list)
            or not isinstance(raw_needs, list)
        ):
            raise RuntimeError("Disaster keyword taxonomy contains an invalid hazard type")
        keywords = tuple(
            keyword
            for keyword in (str(value).strip().lower() for value in raw_keywords)
            if keyword
        )
        needs = tuple(
            need
            for need in (str(value).strip().lower() for value in raw_needs)
            if need
        )
        if not keywords or len(keywords) != len(set(keywords)):
            raise RuntimeError(f"Hazard '{hazard}' has empty or duplicate keywords")
        if any(need not in ALLOCATION_NEEDS for need in needs):
            raise RuntimeError(f"Hazard '{hazard}' has an unsupported allocation need")
        keywords_by_hazard[hazard] = keywords
        needs_by_hazard[hazard] = needs
        all_keywords.extend(keywords)

    if len(all_keywords) != EXPECTED_DISASTER_KEYWORD_COUNT:
        raise RuntimeError(
            f"Disaster keyword taxonomy must contain exactly {EXPECTED_DISASTER_KEYWORD_COUNT} keywords"
        )
    if len(all_keywords) != len(set(all_keywords)):
        raise RuntimeError("Disaster keyword taxonomy contains duplicate keywords")
    return keywords_by_hazard, needs_by_hazard


HAZARD_KEYWORDS, HAZARD_DEFAULT_NEEDS = _load_disaster_taxonomy()


def _compile_keyword_pattern(keyword: str) -> re.Pattern[str]:
    phrase = r"[\s-]+".join(re.escape(part) for part in re.split(r"[\s-]+", keyword))
    return re.compile(rf"(?<!\w){phrase}(?:ing|ed|es|s)?(?!\w)", re.IGNORECASE)


HAZARD_PATTERNS = tuple(
    sorted(
        (
            (hazard, keyword, _compile_keyword_pattern(keyword))
            for hazard, keywords in HAZARD_KEYWORDS.items()
            for keyword in keywords
        ),
        key=lambda item: len(item[1]),
        reverse=True,
    )
)

NEED_KEYWORDS: dict[str, tuple[str, ...]] = {
    "food": ("food", "ration", "meals"),
    "water": ("drinking water", "potable water", "water supply"),
    "shelter": ("shelter", "evacuation centre", "displaced"),
    "medical": ("medical", "injured", "hospital", "first aid"),
    "rescue": ("rescue", "trapped", "missing"),
    "transport": ("road blocked", "access", "transport", "bridge"),
}


def _text(value: Any) -> str:
    return str(value or "").strip()


def parse_datetime(value: Any) -> datetime:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    raw = _text(value)
    if not raw:
        return datetime.now(timezone.utc)
    relative = re.fullmatch(
        r"(?:about\s+)?(\d+)\s+(minute|hour|day|week|month)s?\s+ago",
        raw.lower(),
    )
    if relative:
        amount = int(relative.group(1))
        unit = relative.group(2)
        multipliers = {
            "minute": timedelta(minutes=amount),
            "hour": timedelta(hours=amount),
            "day": timedelta(days=amount),
            "week": timedelta(weeks=amount),
            "month": timedelta(days=30 * amount),
        }
        return datetime.now(timezone.utc) - multipliers[unit]
    for pattern in (
        "%Y%m%dT%H%M%SZ",
        "%a, %d %b %Y %H:%M:%S %z",
        "%b %d, %Y",
        "%d %b %Y",
    ):
        try:
            return datetime.strptime(raw, pattern)
        except ValueError:
            pass
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    except ValueError:
        return datetime.now(timezone.utc)


def classify_hazard(text: str) -> str:
    for hazard, _, pattern in HAZARD_PATTERNS:
        if pattern.search(text):
            return hazard
    return "other"


def extract_needs(text: str) -> list[str]:
    lowered = text.lower()
    return [need for need, words in NEED_KEYWORDS.items() if any(word in lowered for word in words)]


def needs_for_hazard(text: str, hazard: str) -> list[str]:
    explicit = extract_needs(text)
    defaults = HAZARD_DEFAULT_NEEDS.get(hazard, ())
    return list(dict.fromkeys((*explicit, *defaults)))


def resolve_location(text: str) -> tuple[float, float, str] | None:
    lowered = text.lower()
    matches = [(key, value) for key, value in GAZETTEER.items() if key in lowered]
    if not matches:
        return None
    return max(matches, key=lambda item: len(item[0]))[1]


def point_from_geojson(geometry: dict[str, Any]) -> tuple[float, float] | None:
    """Return (latitude, longitude) for a GeoJSON point or polygon centroid."""

    coordinates = geometry.get("coordinates")
    if not isinstance(coordinates, list):
        return None
    points: list[tuple[float, float]] = []

    def collect(value: Any) -> None:
        if (
            isinstance(value, list)
            and len(value) >= 2
            and isinstance(value[0], (int, float))
            and isinstance(value[1], (int, float))
        ):
            longitude, latitude = float(value[0]), float(value[1])
            if -180 <= longitude <= 180 and -90 <= latitude <= 90:
                points.append((latitude, longitude))
            return
        if isinstance(value, list):
            for child in value:
                collect(child)

    collect(coordinates)
    if not points:
        return None
    return (
        sum(point[0] for point in points) / len(points),
        sum(point[1] for point in points) / len(points),
    )


def infer_severity(text: str, hazard: str, supplied: int | None = None) -> int:
    if supplied is not None:
        return max(1, min(5, supplied))
    lowered = text.lower()
    if any(word in lowered for word in ("catastrophic", "red alert", "mass casualty", "major emergency")):
        return 5
    if any(word in lowered for word in ("severe", "evacuation", "extreme", "very heavy", "orange alert")):
        return 4
    if any(word in lowered for word in ("warning", "displaced", "damaged", "blocked")):
        return 3
    return 3 if hazard in {"earthquake", "cyclone"} else 2


def estimate_affected(text: str) -> int:
    patterns = (
        r"([\d,]+)\s+(?:people|persons|residents|families)\s+(?:affected|displaced|evacuated)",
        r"affected\s+(?:about\s+|nearly\s+|over\s+)?([\d,]+)",
        r"(?:affects?|displaces?|evacuates?)\s+(?:about\s+|nearly\s+|over\s+)?([\d,]+)\s+(?:people|persons|residents|families)",
    )
    lowered = text.lower()
    for pattern in patterns:
        match = re.search(pattern, lowered)
        if match:
            return int(match.group(1).replace(",", ""))
    return 0


def normalize_article(
    *,
    title: str,
    description: str,
    url: str,
    published_at: Any,
    source_kind: str,
    external_id: str = "",
    verification_status: str = "unverified",
) -> IncidentCandidate | None:
    combined = f"{title}. {description}".strip()
    hazard = classify_hazard(combined)
    location = resolve_location(combined)
    if hazard == "other" or location is None:
        return None
    latitude, longitude, location_name = location
    stable_id = external_id or hashlib.sha256(f"{title}|{url}".encode()).hexdigest()[:24]
    return IncidentCandidate(
        external_id=stable_id,
        title=title[:240],
        description=description[:1800],
        disaster_type=hazard,
        severity=infer_severity(combined, hazard),
        latitude=latitude,
        longitude=longitude,
        location_name=location_name,
        occurred_at=parse_datetime(published_at),
        source_kind=source_kind,
        verification_status=verification_status,
        source_url=url,
        affected_estimate=estimate_affected(combined),
        needs=needs_for_hazard(combined, hazard),
    )
