from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.adapters.eonet import EonetAdapter
from app.adapters.gdelt import GdeltAdapter
from app.adapters.government import GovernmentFeedAdapter
from app.adapters.reliefweb import ReliefWebAdapter
from app.adapters.usgs import UsgsAdapter
from app.models import Source


def source(adapter_type: str, endpoint: str = "https://example.org/feed") -> Source:
    return Source(
        slug=f"test-{adapter_type}",
        name=f"Test {adapter_type}",
        adapter_type=adapter_type,
        endpoint=endpoint,
        authority="Test authority",
        source_kind="official",
    )


def test_usgs_geojson_maps_magnitude_and_coordinates():
    adapter = UsgsAdapter()
    adapter.get_json = AsyncMock(
        return_value={
            "features": [
                {
                    "id": "quake-1",
                    "properties": {
                        "mag": 6.4,
                        "title": "M 6.4 earthquake",
                        "place": "Example region",
                        "time": 1_786_000_000_000,
                        "url": "https://earthquake.usgs.gov/example",
                    },
                    "geometry": {"type": "Point", "coordinates": [91.0, 26.0, 12.0]},
                }
            ]
        }
    )

    incidents = asyncio.run(adapter.fetch(source("usgs")))

    assert len(incidents) == 1
    assert incidents[0].severity == 4
    assert (incidents[0].latitude, incidents[0].longitude) == (26.0, 91.0)
    assert incidents[0].verification_status == "official"


def test_eonet_accepts_polygon_geometry():
    adapter = EonetAdapter()
    adapter.get_json = AsyncMock(
        return_value={
            "events": [
                {
                    "id": "event-1",
                    "title": "Flooded area",
                    "categories": [{"id": "floods"}],
                    "sources": [{"url": "https://eonet.gsfc.nasa.gov/example"}],
                    "geometry": [
                        {
                            "type": "Polygon",
                            "date": "2026-08-21T00:00:00Z",
                            "coordinates": [[[90.0, 25.0], [92.0, 25.0], [92.0, 27.0], [90.0, 27.0]]],
                        }
                    ],
                }
            ]
        }
    )

    incidents = asyncio.run(adapter.fetch(source("eonet")))

    assert incidents[0].disaster_type == "flood"
    assert (incidents[0].latitude, incidents[0].longitude) == (26.0, 91.0)


def test_gdelt_web_result_runs_through_portal_normalizer():
    adapter = GdeltAdapter()
    adapter.get_json = AsyncMock(
        return_value={
            "articles": [
                {
                    "title": "Severe flood blocks road access in Assam",
                    "url": "https://news.example/assam-flood",
                    "seendate": "20260821T090000Z",
                    "sourcecountry": "India",
                    "domain": "news.example",
                }
            ]
        }
    )

    incidents = asyncio.run(adapter.fetch(source("gdelt")))

    assert len(incidents) == 1
    assert incidents[0].source_kind == "search"
    assert incidents[0].verification_status == "unverified"
    assert incidents[0].location_name == "Assam, India"


def test_reliefweb_report_is_corroborated_not_official(monkeypatch):
    import app.adapters.reliefweb as reliefweb_module

    monkeypatch.setattr(reliefweb_module, "settings", SimpleNamespace(reliefweb_appname="approved-test-app"))
    adapter = ReliefWebAdapter()
    adapter.get_json = AsyncMock(
        return_value={
            "data": [
                {
                    "id": 42,
                    "fields": {
                        "title": "Flood response in Kerala",
                        "body": "Road access is blocked and families need shelter.",
                        "country": [{"name": "India"}],
                        "url": "https://reliefweb.int/example",
                        "date": {"created": "2026-08-21T08:00:00Z"},
                    },
                }
            ]
        }
    )

    incidents = asyncio.run(adapter.fetch(source("reliefweb")))

    assert incidents[0].verification_status == "corroborated"
    assert incidents[0].location_name == "Kerala, India"


def test_cap_rss_point_preserves_official_authority():
    xml = """
    <rss xmlns:cap="urn:oasis:names:tc:emergency:cap:1.2" xmlns:georss="http://www.georss.org/georss">
      <channel><item><guid>alert-7</guid><title>Severe flood warning for Assam</title>
      <description>Evacuation is advised.</description><pubDate>Fri, 21 Aug 2026 09:00:00 +0000</pubDate>
      <georss:point>26.2 92.9</georss:point><cap:severity>Severe</cap:severity>
      <cap:areaDesc>Nagaon, Assam</cap:areaDesc><link>https://mausam.imd.gov.in/alert-7</link>
      </item></channel>
    </rss>
    """

    incidents = GovernmentFeedAdapter()._from_xml(
        xml,
        source("government", "https://mausam.imd.gov.in/feed.xml"),
    )

    assert len(incidents) == 1
    assert incidents[0].severity == 4
    assert incidents[0].verification_status == "official"
    assert incidents[0].location_name == "Nagaon, Assam"
