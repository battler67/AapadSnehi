import pytest

from app.priority import volunteer_fit
from app.services.normalizer import (
    EXPECTED_DISASTER_KEYWORD_COUNT,
    HAZARD_KEYWORDS,
    classify_hazard,
    normalize_article,
    point_from_geojson,
)


ALL_DISASTER_KEYWORDS = [
    (hazard, keyword)
    for hazard, keywords in HAZARD_KEYWORDS.items()
    for keyword in keywords
]


def test_disaster_taxonomy_contains_exactly_53_unique_keywords():
    keywords = [keyword for _, keyword in ALL_DISASTER_KEYWORDS]

    assert len(keywords) == EXPECTED_DISASTER_KEYWORD_COUNT == 53
    assert len(keywords) == len(set(keywords))
    assert {
        "flood",
        "earthquake",
        "landslide",
        "thunderstorm",
        "heavy rain",
    }.issubset(keywords)


@pytest.mark.parametrize(("expected_hazard", "keyword"), ALL_DISASTER_KEYWORDS)
def test_every_configured_disaster_keyword_is_detected(expected_hazard: str, keyword: str):
    assert classify_hazard(f"Emergency bulletin: {keyword} reported") == expected_hazard


@pytest.mark.parametrize(
    ("text", "expected_hazard"),
    [
        ("Flooding affects homes in Assam", "flood"),
        ("Earthquakes shake the region", "earthquake"),
        ("Multiple landslides block roads", "landslide"),
        ("Thunderstorms forecast across Delhi", "storm"),
        ("Heavy rains trigger warnings in Kerala", "heavy_rain"),
        ("Wildfires spread near Himachal villages", "wildfire"),
    ],
)
def test_keyword_matching_recognizes_common_inflections(text: str, expected_hazard: str):
    assert classify_hazard(text) == expected_hazard


def test_keyword_matching_respects_word_boundaries():
    assert classify_hazard("A new brainstorming platform improves firewall monitoring") == "other"


def test_news_normalizer_creates_portal_ready_incident_with_location_evidence():
    incident = normalize_article(
        title="Severe flood displaces 2,400 people in Assam",
        description="Road access is blocked and communities need food and medical support.",
        url="https://example.org/report",
        published_at="2026-08-21T10:00:00Z",
        source_kind="search",
    )

    assert incident is not None
    assert incident.disaster_type == "flood"
    assert incident.location_name == "Assam, India"
    assert incident.affected_estimate == 2400
    assert {"food", "medical", "transport"}.issubset(set(incident.needs))
    assert incident.verification_status == "unverified"


def test_detected_hazard_adds_default_needs_for_volunteer_matching():
    incident = normalize_article(
        title="Thunderstorms damage roads in Assam",
        description="A warning is active across several districts.",
        url="https://example.org/storm",
        published_at="2026-08-21T10:00:00Z",
        source_kind="news",
    )

    assert incident is not None
    assert incident.disaster_type == "storm"
    assert {"shelter", "medical", "transport"}.issubset(incident.needs)

    capable_score, _ = volunteer_fit(
        incident_needs=incident.needs,
        incident_severity=incident.severity,
        incident_latitude=incident.latitude,
        incident_longitude=incident.longitude,
        services=["medical", "transport"],
        skills=[],
        availability="available",
        volunteer_latitude=incident.latitude,
        volunteer_longitude=incident.longitude,
    )
    unrelated_score, _ = volunteer_fit(
        incident_needs=incident.needs,
        incident_severity=incident.severity,
        incident_latitude=incident.latitude,
        incident_longitude=incident.longitude,
        services=["water"],
        skills=[],
        availability="available",
        volunteer_latitude=incident.latitude,
        volunteer_longitude=incident.longitude,
    )

    assert capable_score > unrelated_score


def test_news_normalizer_rejects_unlocated_items_from_map():
    incident = normalize_article(
        title="Flood response continues",
        description="No reliable place is stated in this item.",
        url="https://example.org/unlocated",
        published_at="2026-08-21T10:00:00Z",
        source_kind="news",
    )

    assert incident is None


def test_geojson_polygon_is_reduced_to_a_map_point():
    point = point_from_geojson(
        {
            "type": "Polygon",
            "coordinates": [[[90.0, 25.0], [92.0, 25.0], [92.0, 27.0], [90.0, 27.0]]],
        }
    )

    assert point == (26.0, 91.0)
