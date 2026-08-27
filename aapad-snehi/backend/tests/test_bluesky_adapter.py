from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from app.adapters.base import AdapterConfigurationError
from app.adapters.bluesky import BLUESKY_SERVICE, BlueskyAdapter
from app.models import Source


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


def fake_settings(**overrides):
    values = {
        "bluesky_email": "account@example.test",
        "bluesky_app_password": "test-app-password",
        "bluesky_query": "floods in india",
        "bluesky_max_posts": 10,
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
    assert result.authors[0].post_url.startswith("https://bsky.app/profile/")


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
