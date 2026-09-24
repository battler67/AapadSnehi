from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from app.adapters.base import AdapterConfigurationError
from app.adapters.bluesky import BLUESKY_SERVICE, BlueskyAdapter
from app.models import Source
from app.services.sentiment import SentimentResult


def post(*, did: str, handle: str, text: str, key: str):
    return SimpleNamespace(
        uri=f"at://{did}/app.bsky.feed.post/{key}",
        author=SimpleNamespace(did=did, handle=handle, display_name="Helpful account"),
        record=SimpleNamespace(
            text=text,
            created_at=datetime.now(timezone.utc).isoformat(),
        ),
    )


class FakeClient:
    def __init__(self, posts):
        self.posts = posts
        self.login_args = None
        self.search_params = None
        self.app = SimpleNamespace(
            bsky=SimpleNamespace(
                feed=SimpleNamespace(search_posts=self.search_posts),
            )
        )

    def login(self, email, password):
        self.login_args = (email, password)

    def search_posts(self, *, params):
        self.search_params = params
        return SimpleNamespace(posts=self.posts)


class FakeSentimentAnalyzer:
    def __init__(self, label="positive", score=0.85):
        self.label = label
        self.score = score
        self.model = "fake-sentiment-model"
        self.texts = []

    def classify(self, text):
        self.texts.append(text)
        return SentimentResult(
            label=self.label,
            score=self.score,
            model="fake-sentiment-model",
            status="available",
        )


def fake_settings(**overrides):
    values = {
        "bluesky_email": "account@example.test",
        "bluesky_app_password": "test-app-password",
        "bluesky_query": "floods in india",
        "bluesky_max_posts": 10,
        "hf_token": "",
        "bluesky_sentiment_enabled": False,
        "bluesky_sentiment_model": "cardiffnlp/twitter-roberta-base-sentiment-latest",
        "bluesky_sentiment_max_posts": 10,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def test_authenticated_scan_returns_only_unique_explicit_helpers(monkeypatch):
    import app.adapters.bluesky as bluesky_module

    client = FakeClient(
        [
            post(
                did="did:plc:helper",
                handle="helper.example",
                text="Assam flood: our team can help with food and boat rescue.",
                key="offer-1",
            ),
            post(
                did="did:plc:requester",
                handle="requester.example",
                text="Assam flood: we need urgent help and food.",
                key="request-1",
            ),
            post(
                did="did:plc:helper",
                handle="helper.example",
                text="Assam flood: we are ready to help with transport.",
                key="offer-2",
            ),
            post(
                did="did:plc:cheerful",
                handle="cheerful.example",
                text="What a wonderful day!",
                key="positive-1",
            ),
        ]
    )
    monkeypatch.setattr(bluesky_module, "settings", fake_settings())

    result = asyncio.run(
        BlueskyAdapter(client_factory=lambda: client).scan_authors()
    )

    assert client.login_args == ("account@example.test", "test-app-password")
    assert client.search_params == {"q": "floods in india", "limit": 10}
    assert result.scanned_count == 4
    assert len(result.authors) == 1
    assert result.authors[0].author_did == "did:plc:helper"
    assert result.authors[0].author_handle == "helper.example"
    assert result.authors[0].confidence == "high"
    assert result.authors[0].intent_category == "explicit_offer"
    assert result.authors[0].disaster_context == "post"
    assert result.authors[0].post_url.startswith("https://bsky.app/profile/")


def test_query_context_includes_thread_aid_and_keeps_strongest_author_post(monkeypatch):
    import app.adapters.bluesky as bluesky_module

    client = FakeClient(
        [
            post(did="did:plc:ngo", handle="ngo.example", text="Please support affected families through our relief appeal.", key="appeal"),
            post(did="did:plc:ngo", handle="ngo.example", text="Our experts are providing psychological first aid to residents.", key="active-aid"),
            post(did="did:plc:news", handle="news.example", text="Nepal flood recovery remains difficult.", key="news-only"),
        ]
    )
    monkeypatch.setattr(bluesky_module, "settings", fake_settings())

    result = asyncio.run(
        BlueskyAdapter(client_factory=lambda: client).scan_authors("Nepal flood relief")
    )

    assert len(result.authors) == 1
    match = result.authors[0]
    assert match.author_did == "did:plc:ngo"
    assert match.post_uri.endswith("/active-aid")
    assert match.disaster_type == "flood"
    assert match.disaster_context == "query"
    assert match.intent_category == "active_assistance"
    assert match.confidence == "medium"


def test_low_confidence_fundraiser_is_visible_but_not_ingested(monkeypatch):
    import app.adapters.bluesky as bluesky_module

    client = FakeClient(
        [
            post(
                did="did:plc:fundraiser",
                handle="fundraiser.example",
                text="A restaurant will donate ten percent of sales to Nepal flood relief.",
                key="fundraiser",
            )
        ]
    )
    monkeypatch.setattr(bluesky_module, "settings", fake_settings())
    adapter = BlueskyAdapter(client_factory=lambda: client)
    scan = asyncio.run(adapter.scan_authors("Nepal flood relief"))
    source = Source(
        slug="test-bluesky",
        name="Test Bluesky",
        adapter_type="bluesky",
        endpoint=BLUESKY_SERVICE,
        authority="Authenticated Bluesky search",
        source_kind="social",
    )

    incidents = asyncio.run(adapter.fetch(source))

    assert len(scan.authors) == 1
    assert scan.authors[0].confidence == "low"
    assert incidents == []


def test_sentiment_is_advisory_and_only_runs_for_matched_authors(monkeypatch):
    import app.adapters.bluesky as bluesky_module

    client = FakeClient(
        [
            post(
                did="did:plc:helper",
                handle="helper.example",
                text="Nepal flood: our team can help provide shelter.",
                key="helper",
            ),
            post(
                did="did:plc:positive-news",
                handle="positive-news.example",
                text="Wonderful hopeful news from Nepal today!",
                key="positive-news",
            ),
        ]
    )
    sentiment = FakeSentimentAnalyzer()
    monkeypatch.setattr(bluesky_module, "settings", fake_settings())

    result = asyncio.run(
        BlueskyAdapter(
            client_factory=lambda: client,
            sentiment_analyzer=sentiment,
        ).scan_authors("Nepal flood")
    )

    assert len(result.authors) == 1
    assert result.authors[0].sentiment_label == "positive"
    assert result.authors[0].sentiment_score == 0.85
    assert sentiment.texts == ["Nepal flood: our team can help provide shelter."]
    assert result.as_dict()["sentimentSummary"] == {
        "positive": 1,
        "neutral": 0,
        "negative": 0,
        "unavailable": 0,
    }


def test_sentiment_calls_are_bounded_per_scan(monkeypatch):
    import app.adapters.bluesky as bluesky_module

    client = FakeClient(
        [
            post(did="did:plc:a", handle="a.example", text="Nepal flood: we can help with food.", key="a"),
            post(did="did:plc:b", handle="b.example", text="Nepal flood: we can help with shelter.", key="b"),
        ]
    )
    sentiment = FakeSentimentAnalyzer()
    monkeypatch.setattr(
        bluesky_module,
        "settings",
        fake_settings(bluesky_sentiment_max_posts=1),
    )

    result = asyncio.run(
        BlueskyAdapter(
            client_factory=lambda: client,
            sentiment_analyzer=sentiment,
        ).scan_authors("Nepal flood")
    )

    assert len(sentiment.texts) == 1
    assert result.authors[0].sentiment_status == "available"
    assert result.authors[1].sentiment_status == "limit_reached"


def test_fetch_keeps_bluesky_incident_unverified(monkeypatch):
    import app.adapters.bluesky as bluesky_module

    client = FakeClient(
        [
            post(
                did="did:plc:helper",
                handle="helper.example",
                text="Assam flood: our team can help with food and boat rescue.",
                key="offer-1",
            )
        ]
    )
    monkeypatch.setattr(bluesky_module, "settings", fake_settings())
    source = Source(
        slug="test-bluesky",
        name="Test Bluesky",
        adapter_type="bluesky",
        endpoint=BLUESKY_SERVICE,
        authority="Authenticated Bluesky search",
        source_kind="social",
    )

    incidents = asyncio.run(
        BlueskyAdapter(client_factory=lambda: client).fetch(source)
    )

    assert len(incidents) == 1
    assert incidents[0].source_kind == "social"
    assert incidents[0].verification_status == "unverified"


def test_missing_credentials_reports_configuration_error(monkeypatch):
    import app.adapters.bluesky as bluesky_module

    monkeypatch.setattr(
        bluesky_module,
        "settings",
        fake_settings(bluesky_email="", bluesky_app_password=""),
    )

    with pytest.raises(AdapterConfigurationError, match="AAPAD_BLUESKY_EMAIL"):
        asyncio.run(BlueskyAdapter(client_factory=lambda: FakeClient([])).scan_authors())
