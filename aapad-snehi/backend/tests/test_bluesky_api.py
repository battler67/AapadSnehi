from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

from app.adapters.bluesky import BlueskyAuthorMatch, BlueskyScanResult


def test_bluesky_demo_scan_returns_author_ids(
    client,
    monkeypatch,
):
    import app.main as main_module

    async def fake_scan(self, query):
        del self
        return BlueskyScanResult(
            query=query,
            scanned_count=3,
            authors=(
                BlueskyAuthorMatch(
                    author_did="did:plc:api-helper",
                    author_handle="api-helper.example",
                    display_name="API Helper",
                    post_uri="at://did:plc:api-helper/app.bsky.feed.post/offer",
                    post_url="https://bsky.app/profile/did:plc:api-helper/post/offer",
                    post_text="Assam flood: our team can help with food.",
                    posted_at=datetime.now(timezone.utc),
                    disaster_type="flood",
                    disaster_context="post",
                    intent_category="explicit_offer",
                    confidence="high",
                    matched_terms=("can help",),
                    capabilities=("food", "volunteering"),
                ),
            ),
        )

    monkeypatch.setattr(
        main_module,
        "settings",
        SimpleNamespace(enable_live_adapters=True),
    )
    monkeypatch.setattr(main_module.BlueskyAdapter, "scan_authors", fake_scan)

    response = client.post(
        "/api/bluesky/scan",
        json={"query": "flood India"},
    )

    assert response.status_code == 200, response.text
    assert response.json()["scannedCount"] == 3
    assert response.json()["matchCount"] == 1
    assert response.json()["authors"][0]["id"] == "did:plc:api-helper"
    assert response.json()["authors"][0]["confidence"] == "high"
    assert response.json()["authors"][0]["disasterContext"] == "post"
    assert response.json()["sentimentSummary"]["unavailable"] == 1
