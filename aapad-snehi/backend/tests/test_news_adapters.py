from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.adapters import get_adapter, registered_adapter_types
from app.adapters.base import AdapterConfigurationError
from app.adapters.google_news import GoogleNewsRssAdapter, validate_google_news_url
from app.adapters.serper import SerperSearchAdapter, validate_serper_url
from app.models import Source


def source(adapter_type: str, endpoint: str) -> Source:
    return Source(
        slug=f"test-{adapter_type}",
        name=f"Test {adapter_type}",
        adapter_type=adapter_type,
        endpoint=endpoint,
        authority="Test authority",
        source_kind="search" if adapter_type == "serper" else "news",
    )


def test_registry_discovers_builtin_and_news_adapters():
    expected = {
        "seed",
        "usgs",
        "eonet",
        "reliefweb",
        "gdelt",
        "government",
        "serper",
        "google_news",
    }
    assert expected.issubset(set(registered_adapter_types()))
    assert get_adapter("serper") is SerperSearchAdapter
    assert get_adapter("google_news") is GoogleNewsRssAdapter


def test_serper_returns_first_five_ranked_disaster_results(monkeypatch):
    import app.adapters.serper as serper_module

    monkeypatch.setattr(
        serper_module,
        "settings",
        SimpleNamespace(serper_api_key="test-api-key-placeholder"),
    )
    adapter = SerperSearchAdapter()
    adapter.post_json = AsyncMock(
        return_value={
            "organic": [
                {"position": 7, "title": "Himachal forest fire blocks road access", "snippet": "India response teams deployed", "link": "https://example.org/7", "date": "1 day ago"},
                {"position": 2, "title": "India technology investment rises", "snippet": "Artificial intelligence funding", "link": "https://example.org/2", "date": "2 hours ago"},
                {"position": 5, "title": "Delhi heatwave warning", "snippet": "Extreme heat affects residents in India", "link": "https://example.org/5", "date": "4 hours ago"},
                {"position": 1, "title": "Severe Assam flood blocks access", "snippet": "Families displaced in India", "link": "https://example.org/1", "date": "1 hour ago"},
                {"position": 6, "title": "Sikkim earthquake response", "snippet": "Tremor reported in India", "link": "https://example.org/6", "date": "6 hours ago"},
                {"position": 4, "title": "Uttarakhand landslide warning", "snippet": "Road blocked in India", "link": "https://example.org/4", "date": "3 hours ago"},
                {"position": 3, "title": "Cyclone approaches Odisha", "snippet": "Evacuation warning issued in India", "link": "https://example.org/3", "date": "2 hours ago"},
            ]
        }
    )

    incidents = asyncio.run(
        adapter.fetch(source("serper", "https://google.serper.dev/search"))
    )

    assert len(incidents) == 5
    assert incidents[0].title == "Severe Assam flood blocks access"
    assert all(item.verification_status == "unverified" for item in incidents)
    assert all(item.source_kind == "search" for item in incidents)
    assert all(item.title != "India technology investment rises" for item in incidents)
    assert incidents[0].occurred_at < datetime.now(timezone.utc)
    request = adapter.post_json.await_args
    assert request.kwargs["json_payload"]["gl"] == "in"
    assert request.kwargs["json_payload"]["hl"] == "en"
    assert request.kwargs["json_payload"]["num"] == 20
    assert request.kwargs["headers"]["X-API-KEY"] == "test-api-key-placeholder"


def test_serper_requires_environment_key(monkeypatch):
    import app.adapters.serper as serper_module

    monkeypatch.setattr(serper_module, "settings", SimpleNamespace(serper_api_key=""))
    with pytest.raises(AdapterConfigurationError, match="AAPAD_SERPER_API_KEY"):
        asyncio.run(
            SerperSearchAdapter().fetch(
                source("serper", "https://google.serper.dev/search")
            )
        )


@pytest.mark.parametrize(
    "url",
    [
        "http://google.serper.dev/search",
        "https://example.org/search",
        "https://user:pass@google.serper.dev/search",
        "https://google.serper.dev/places",
    ],
)
def test_serper_rejects_unreviewed_endpoints(url: str):
    with pytest.raises(AdapterConfigurationError):
        validate_serper_url(url)


def test_google_news_rss_filters_and_limits_disaster_results():
    items = [
        ("flood-1", "Assam flood displaces families", "Flood water blocks road access", "Fri, 21 Aug 2026 09:00:00 +0000"),
        ("tech", "India technology conference opens", "New artificial intelligence products", "Fri, 21 Aug 2026 08:30:00 +0000"),
        ("cyclone-2", "Odisha cyclone evacuation begins", "Severe storm warning", "Fri, 21 Aug 2026 08:00:00 +0000"),
        ("slide-3", "Uttarakhand landslide blocks highway", "Rescue teams need access", "Fri, 21 Aug 2026 07:00:00 +0000"),
        ("heat-4", "Delhi heatwave warning extended", "Extreme heat affects residents", "Fri, 21 Aug 2026 06:00:00 +0000"),
        ("quake-5", "Sikkim earthquake reported", "Tremor prompts verification", "Fri, 21 Aug 2026 05:00:00 +0000"),
        ("fire-6", "Himachal forest fire spreads", "Road blocked near villages", "Fri, 21 Aug 2026 04:00:00 +0000"),
    ]
    xml_items = "".join(
        f"<item><guid>{identifier}</guid><title>{title}</title>"
        f"<description><![CDATA[<p>{description}</p>]]></description>"
        f"<link>https://news.example/{identifier}</link><pubDate>{published}</pubDate></item>"
        for identifier, title, description, published in items
    )
    adapter = GoogleNewsRssAdapter()
    adapter.get_text = AsyncMock(
        return_value=(f"<rss><channel>{xml_items}</channel></rss>", "application/rss+xml")
    )

    incidents = asyncio.run(
        adapter.fetch(
            source(
                "google_news",
                "https://news.google.com/rss?hl=en-IN&gl=IN&ceid=IN:en",
            )
        )
    )

    assert len(incidents) == 5
    assert incidents[0].external_id == "flood-1"
    assert all(item.verification_status == "unverified" for item in incidents)
    assert all(item.source_kind == "news" for item in incidents)
    assert all("technology conference" not in item.title for item in incidents)


@pytest.mark.parametrize(
    "url",
    [
        "http://news.google.com/rss",
        "https://example.org/rss",
        "https://user:pass@news.google.com/rss",
        "https://news.google.com/articles/example",
    ],
)
def test_google_news_rejects_unreviewed_feed_urls(url: str):
    with pytest.raises(AdapterConfigurationError):
        validate_google_news_url(url)


def test_requested_news_sources_are_visible_through_api(client):
    response = client.get("/api/sources")
    assert response.status_code == 200
    slugs = {item["slug"] for item in response.json()}
    assert {
        "serper-india-disasters",
        "google-news-india-headlines",
        "google-news-ai",
        "google-news-india-technology",
    }.issubset(slugs)


def test_serper_snapshot_flows_into_dashboard_top_five(client, monkeypatch):
    import app.adapters.serper as serper_module
    import app.services.ingestion as ingestion_module

    monkeypatch.setattr(
        serper_module,
        "settings",
        SimpleNamespace(serper_api_key="test-api-key-placeholder"),
    )
    monkeypatch.setattr(
        ingestion_module,
        "settings",
        SimpleNamespace(enable_live_adapters=True),
    )
    results = [
        {
            "position": position,
            "title": f"Severe Assam flood incident {position}",
            "snippet": "Families displaced and road access blocked in India",
            "link": f"https://example.org/dashboard-{position}",
            "date": f"{position} hours ago",
        }
        for position in range(1, 7)
    ]
    mocked_post = AsyncMock(return_value={"organic": results})
    monkeypatch.setattr(SerperSearchAdapter, "post_json", mocked_post)
    sources = client.get("/api/sources").json()
    serper_source = next(item for item in sources if item["adapterType"] == "serper")

    first = client.post(
        "/api/ingestion/run",
        json={"source_ids": [serper_source["id"]], "live": True},
    )

    assert first.status_code == 200, first.text
    assert first.json()[0]["fetchedCount"] == 5
    dashboard = client.get("/api/dashboard").json()
    assert len(dashboard["externalIncidents"]) == 5
    assert all(
        item["sourceName"] == "Serper India disaster search"
        for item in dashboard["externalIncidents"]
    )

    mocked_post.return_value = {"organic": results[:1]}
    second = client.post(
        "/api/ingestion/run",
        json={"source_ids": [serper_source["id"]], "live": True},
    )

    assert second.status_code == 200, second.text
    assert len(client.get("/api/dashboard").json()["externalIncidents"]) == 1
