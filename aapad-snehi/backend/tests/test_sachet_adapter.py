from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from email.utils import format_datetime
from unittest.mock import AsyncMock
from urllib.parse import parse_qs, urlparse

import httpx
import pytest

from app.adapters import get_adapter, registered_adapter_types
from app.adapters.base import AdapterConfigurationError, AdapterError, AdapterResponse
from app.adapters.sachet import (
    SachetCapRssAdapter,
    validate_sachet_cap_url,
    validate_sachet_feed_url,
    validate_sachet_polygon_url,
)
from app.models import Source


FEED_URL = "https://sachet.ndma.gov.in/cap_public_website/rss/rss_india.xml"
CAP_URL = (
    "https://sachet.ndma.gov.in/cap_public_website/"
    "FetchXMLFile?identifier=1787061695443006"
)
POLYGON_URL = (
    "https://sachet.ndma.gov.in/cap_public_website/"
    "FetchPolygonXMLFile?identifier=1787061695443006"
)


@pytest.fixture(autouse=True)
def clear_sachet_etag_cache():
    SachetCapRssAdapter._etag_cache.clear()
    yield
    SachetCapRssAdapter._etag_cache.clear()


def source() -> Source:
    return Source(
        slug="sachet-india-test",
        name="SACHET India CAP alerts",
        adapter_type="sachet",
        endpoint=FEED_URL,
        authority="NDMA SACHET / authorized Indian alerting agencies",
        source_kind="official",
    )


def response(
    body: str = "",
    *,
    status: int = 200,
    etag: str = "",
) -> AdapterResponse:
    return AdapterResponse(
        body=body.encode(),
        content_type="application/xml",
        status_code=status,
        headers={"ETag": etag} if etag else {},
    )


def rss_xml(*, link: str = CAP_URL, title: str = "भारत में आपदा चेतावनी") -> str:
    return f"""
    <rss version="2.0"><channel><title>All India alerts</title><item>
      <title>{title}</title>
      <description />
      <category>Met</category>
      <link>{link.replace('&', '&amp;')}</link>
      <guid>1787061695443006</guid>
      <pubDate>{format_datetime(datetime.now(timezone.utc))}</pubDate>
    </item></channel></rss>
    """


def cap_xml(
    *,
    event: str = "Swell Surge Warning",
    severity: str = "Extreme",
    status: str = "Actual",
    message_type: str = "Update",
    expires: datetime | None = None,
    identifier: str = "IN-1787061695443006_6",
    sender: str = "West-Bengal-SDMA",
    area_xml: str = "<cap:areaDesc>Coastal zones of WEST BENGAL</cap:areaDesc>",
    polygon_url: str = "",
) -> str:
    now = datetime.now(timezone.utc)
    expiry = expires or now + timedelta(days=1)
    return f"""
    <cap:alert xmlns:cap="urn:oasis:names:tc:emergency:cap:1.2">
      <cap:identifier>{identifier}</cap:identifier>
      <cap:sender>{sender}</cap:sender>
      <cap:sent>{now.isoformat()}</cap:sent>
      <cap:status>{status}</cap:status>
      <cap:msgType>{message_type}</cap:msgType>
      <cap:scope>Public</cap:scope>
      <cap:info>
        <cap:language>ml-IN</cap:language>
        <cap:category>Geo</cap:category>
        <cap:event>{event}</cap:event>
        <cap:severity>{severity}</cap:severity>
        <cap:expires>{expiry.isoformat()}</cap:expires>
        <cap:headline>तटीय क्षेत्र में सावधानी बरतें</cap:headline>
        <cap:area><cap:areaDesc>भारत</cap:areaDesc></cap:area>
      </cap:info>
      <cap:info>
        <cap:language>en-IN</cap:language>
        <cap:category>Geo</cap:category>
        <cap:event>{event}</cap:event>
        <cap:urgency>Immediate</cap:urgency>
        <cap:severity>{severity}</cap:severity>
        <cap:certainty>Possible</cap:certainty>
        <cap:expires>{expiry.isoformat()}</cap:expires>
        <cap:headline>Swell surge warning for the West Bengal coast</cap:headline>
        <cap:instruction>Small vessels should not operate near the coast.</cap:instruction>
        {f'<cap:parameter><cap:valueName>Polygon URL</cap:valueName><cap:value>{polygon_url.replace("&", "&amp;")}</cap:value></cap:parameter>' if polygon_url else ''}
        <cap:area>
          {area_xml}
        </cap:area>
      </cap:info>
    </cap:alert>
    """


def test_registry_discovers_sachet_adapter():
    assert "sachet" in registered_adapter_types()
    assert get_adapter("sachet") is SachetCapRssAdapter


def test_sachet_url_validation_accepts_reviewed_feed_and_cap_shapes():
    assert validate_sachet_feed_url(FEED_URL) == FEED_URL
    assert validate_sachet_cap_url(CAP_URL) == CAP_URL
    assert validate_sachet_polygon_url(POLYGON_URL) == POLYGON_URL


@pytest.mark.parametrize(
    "url",
    [
        "http://sachet.ndma.gov.in/cap_public_website/rss/rss_india.xml",
        "https://example.org/cap_public_website/rss/rss_india.xml",
        "https://user:pass@sachet.ndma.gov.in/cap_public_website/rss/rss_india.xml",
        "https://sachet.ndma.gov.in/cap_public_website/rss/rss_kerala.xml",
        "https://sachet.ndma.gov.in/cap_public_website/rss/rss_india.xml?redirect=1",
    ],
)
def test_sachet_feed_rejects_unreviewed_urls(url: str):
    with pytest.raises(AdapterConfigurationError):
        validate_sachet_feed_url(url)


@pytest.mark.parametrize(
    "url",
    [
        "https://example.org/cap_public_website/FetchXMLFile?identifier=123",
        "https://sachet.ndma.gov.in/cap_public_website/FetchXMLFile",
        "https://sachet.ndma.gov.in/cap_public_website/FetchXMLFile?identifier=123&next=x",
        "https://sachet.ndma.gov.in/cap_public_website/FetchPolygonXMLFile?identifier=123",
    ],
)
def test_sachet_rejects_untrusted_linked_cap_urls(url: str):
    with pytest.raises((AdapterConfigurationError, ValueError)):
        validate_sachet_cap_url(url)


@pytest.mark.parametrize(
    "url",
    [
        "https://example.org/cap_public_website/FetchPolygonXMLFile?identifier=123",
        "https://sachet.ndma.gov.in/cap_public_website/FetchPolygonXMLFile",
        "https://sachet.ndma.gov.in/cap_public_website/FetchPolygonXMLFile?identifier=123&next=x",
        "https://sachet.ndma.gov.in/cap_public_website/FetchXMLFile?identifier=123",
    ],
)
def test_sachet_rejects_untrusted_linked_polygon_urls(url: str):
    with pytest.raises((AdapterConfigurationError, ValueError)):
        validate_sachet_polygon_url(url)


def test_sachet_prefers_english_cap_and_accepts_official_event_without_news_keyword():
    adapter = SachetCapRssAdapter()
    adapter.request_with_metadata = AsyncMock(
        side_effect=[
            response(rss_xml(), etag='W/"feed-v1"'),
            response(cap_xml(), etag='"cap-v1"'),
        ]
    )

    incidents = asyncio.run(adapter.fetch(source()))

    assert len(incidents) == 1
    incident = incidents[0]
    assert incident.external_id == "IN-1787061695443006_6"
    assert incident.title == "Swell surge warning for the West Bengal coast"
    assert incident.disaster_type == "swell_surge"
    assert incident.severity == 5
    assert incident.location_name == "Coastal zones of WEST BENGAL"
    assert (incident.latitude, incident.longitude) == (22.9868, 87.855)
    assert incident.needs == ["transport", "rescue"]
    assert incident.source_kind == "official"
    assert incident.verification_status == "official"
    assert incident.source_url == CAP_URL


def test_sachet_fetches_and_parses_linked_polygon_xml():
    adapter = SachetCapRssAdapter()
    adapter.request_with_metadata = AsyncMock(
        side_effect=[
            response(rss_xml()),
            response(
                cap_xml(
                    area_xml="<cap:areaDesc>some parts</cap:areaDesc>",
                    polygon_url=POLYGON_URL,
                )
            ),
            response(
                "<geometry><polygon>22.0,88.0 24.0,90.0 23.0,89.0</polygon></geometry>"
            ),
        ]
    )

    incidents = asyncio.run(adapter.fetch(source()))

    assert len(incidents) == 1
    assert (incidents[0].latitude, incidents[0].longitude) == (23.0, 89.0)
    assert incidents[0].location_name == "West Bengal, India"


def test_sachet_parses_inline_circle_and_geocode_location_evidence():
    area_xml = """
      <cap:areaDesc>some parts</cap:areaDesc>
      <cap:circle>26.2,92.9 50</cap:circle>
      <cap:geocode><cap:valueName>state</cap:valueName><cap:value>Assam</cap:value></cap:geocode>
    """
    adapter = SachetCapRssAdapter()
    adapter.request_with_metadata = AsyncMock(
        side_effect=[
            response(rss_xml()),
            response(cap_xml(sender="IMD-Guwahati", area_xml=area_xml)),
        ]
    )

    incidents = asyncio.run(adapter.fetch(source()))

    assert len(incidents) == 1
    assert (incidents[0].latitude, incidents[0].longitude) == (26.2, 92.9)
    assert incidents[0].location_name == "Assam, India"


def test_sachet_polygon_failure_degrades_to_cap_location_without_failing_feed():
    request = httpx.Request("GET", POLYGON_URL)
    forbidden = httpx.Response(403, request=request)
    adapter = SachetCapRssAdapter()
    adapter.request_with_metadata = AsyncMock(
        side_effect=[
            response(rss_xml()),
            response(
                cap_xml(
                    area_xml="<cap:areaDesc>some parts</cap:areaDesc>",
                    polygon_url=POLYGON_URL,
                )
            ),
            httpx.HTTPStatusError("forbidden", request=request, response=forbidden),
        ]
    )

    incidents = asyncio.run(adapter.fetch(source()))

    assert len(incidents) == 1
    assert incidents[0].location_name == "West Bengal, India"
    assert (incidents[0].latitude, incidents[0].longitude) == (22.9868, 87.855)


def test_sachet_processes_all_india_feed_items_with_bounded_concurrency():
    item_count = 30
    items = "".join(
        f"<item><title>Flood warning in Assam</title><category>Met</category>"
        f"<link>https://sachet.ndma.gov.in/cap_public_website/FetchXMLFile?identifier={index}</link>"
        f"<guid>{index}</guid><pubDate>{format_datetime(datetime.now(timezone.utc))}</pubDate></item>"
        for index in range(item_count)
    )
    feed = f"<rss><channel>{items}</channel></rss>"
    active = 0
    maximum_active = 0

    async def request_provider(method: str, url: str, **_: object) -> AdapterResponse:
        nonlocal active, maximum_active
        if url == FEED_URL:
            return response(feed)
        identifier = parse_qs(urlparse(url).query)["identifier"][0]
        active += 1
        maximum_active = max(maximum_active, active)
        await asyncio.sleep(0.002)
        active -= 1
        return response(
            cap_xml(
                event="Flood Warning",
                severity="Moderate",
                identifier=f"IN-{identifier}",
                sender="Assam-SDMA",
                area_xml="<cap:areaDesc>Assam</cap:areaDesc>",
            )
        )

    adapter = SachetCapRssAdapter()
    adapter.request_with_metadata = AsyncMock(side_effect=request_provider)

    incidents = asyncio.run(adapter.fetch(source()))

    assert len(incidents) == item_count
    assert len({incident.external_id for incident in incidents}) == item_count
    assert 1 < maximum_active <= 8


def test_sachet_uses_loose_bounded_rss_fallback_when_cap_is_temporarily_unavailable():
    adapter = SachetCapRssAdapter()
    adapter.request_with_metadata = AsyncMock(
        side_effect=[response(rss_xml()), AdapterError("temporary provider failure")]
    )

    incidents = asyncio.run(adapter.fetch(source()))

    assert len(incidents) == 1
    incident = incidents[0]
    assert incident.disaster_type == "storm"
    assert incident.verification_status == "official"
    assert incident.location_name == "India"
    assert "temporarily unavailable" in incident.description


@pytest.mark.parametrize(
    "document",
    [
        cap_xml(expires=datetime.now(timezone.utc) - timedelta(minutes=1)),
        cap_xml(message_type="Cancel"),
        cap_xml(status="Exercise"),
    ],
)
def test_sachet_filters_expired_cancelled_and_non_actual_cap_alerts(document: str):
    adapter = SachetCapRssAdapter()
    adapter.request_with_metadata = AsyncMock(
        side_effect=[response(rss_xml()), response(document)]
    )

    assert asyncio.run(adapter.fetch(source())) == []


def test_sachet_reuses_etag_cached_feed_and_cap_on_304():
    adapter = SachetCapRssAdapter()
    adapter.request_with_metadata = AsyncMock(
        side_effect=[
            response(rss_xml(), etag='W/"feed-v1"'),
            response(cap_xml(), etag='"cap-v1"'),
            response(status=304),
            response(status=304),
        ]
    )

    first = asyncio.run(adapter.fetch(source()))
    second = asyncio.run(adapter.fetch(source()))

    assert [item.external_id for item in first] == [item.external_id for item in second]
    calls = adapter.request_with_metadata.await_args_list
    assert calls[2].kwargs["headers"] == {"If-None-Match": 'W/"feed-v1"'}
    assert calls[3].kwargs["headers"] == {"If-None-Match": '"cap-v1"'}
    assert all(call.kwargs["allow_not_modified"] is True for call in calls)
    assert calls[0].kwargs["client"] is calls[1].kwargs["client"]
    assert calls[2].kwargs["client"] is calls[3].kwargs["client"]
    assert calls[0].kwargs["client"] is not calls[2].kwargs["client"]


def test_sachet_source_is_visible_through_api(client):
    response_payload = client.get("/api/sources").json()
    sachet_sources = [item for item in response_payload if item["adapterType"] == "sachet"]
    assert len(sachet_sources) == 1
    sachet_source = sachet_sources[0]
    assert sachet_source["slug"] == "sachet-india"
    assert sachet_source["adapterType"] == "sachet"
    assert sachet_source["sourceKind"] == "official"
    assert sachet_source["endpoint"] == FEED_URL


def test_sachet_incident_flows_into_dashboard_external_signals(client, monkeypatch):
    import app.services.ingestion as ingestion_module

    monkeypatch.setattr(
        ingestion_module,
        "settings",
        type("LiveSettings", (), {"enable_live_adapters": True})(),
    )
    mocked_request = AsyncMock(
        side_effect=[response(rss_xml()), response(cap_xml(event="Flood Warning", severity="Severe"))]
    )
    monkeypatch.setattr(SachetCapRssAdapter, "request_with_metadata", mocked_request)
    sources = client.get("/api/sources").json()
    sachet_source = next(item for item in sources if item["adapterType"] == "sachet")

    run = client.post(
        "/api/ingestion/run",
        json={"source_ids": [sachet_source["id"]], "live": True},
    )

    assert run.status_code == 200, run.text
    assert run.json()[0]["fetchedCount"] == 1
    external = client.get("/api/dashboard").json()["externalIncidents"]
    sachet_incident = next(item for item in external if item["sourceName"] == sachet_source["name"])
    assert sachet_incident["verificationStatus"] == "official"
    assert sachet_incident["disasterType"] == "flood"



def test_sachet_scheduler_runs_only_the_enabled_national_source(monkeypatch):
    import app.services.sachet_scheduler as scheduler_module

    class FakeSession:
        def __enter__(self):
            return self

        def __exit__(self, *_: object) -> None:
            return None

        def scalar(self, _: object) -> int:
            return 41

    fake_session = FakeSession()
    mocked_ingestion = AsyncMock(return_value=[object()])
    monkeypatch.setattr(scheduler_module, "SessionLocal", lambda: fake_session)
    monkeypatch.setattr(scheduler_module, "run_ingestion", mocked_ingestion)

    run_count = asyncio.run(scheduler_module.poll_sachet_once())

    assert run_count == 1
    mocked_ingestion.assert_awaited_once_with(
        fake_session,
        source_ids=[41],
        live=True,
    )
