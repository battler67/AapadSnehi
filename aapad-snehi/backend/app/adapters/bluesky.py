from __future__ import annotations

import asyncio
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from typing import Any
from urllib.parse import quote

from ..config import settings
from ..models import Source
from ..schemas import IncidentCandidate
from ..services.normalizer import classify_hazard, normalize_article
from ..services.social_intent import classify_help_intent
from ..services.sentiment import HuggingFaceSentimentAnalyzer
from .base import AdapterConfigurationError, AdapterError, BaseAdapter
from .registry import register_adapter


try:
    from atproto import Client as AtprotoClient
except ImportError:  # The API can still start and report a clear configuration error.
    AtprotoClient = None


BLUESKY_SERVICE = "https://bsky.social"


@dataclass(frozen=True)
class BlueskyAuthorMatch:
    author_did: str
    author_handle: str
    display_name: str
    post_uri: str
    post_url: str
    post_text: str
    posted_at: datetime
    disaster_type: str
    disaster_context: str
    intent_category: str
    confidence: str
    matched_terms: tuple[str, ...]
    capabilities: tuple[str, ...]
    sentiment_label: str = "unavailable"
    sentiment_score: float | None = None
    sentiment_model: str = ""
    sentiment_status: str = "unavailable"

    def as_dict(self) -> dict[str, Any]:
        return {
            "id": self.author_did,
            "handle": self.author_handle,
            "displayName": self.display_name,
            "postUri": self.post_uri,
            "postUrl": self.post_url,
            "postText": self.post_text,
            "postedAt": self.posted_at.isoformat(),
            "disasterType": self.disaster_type,
            "disasterContext": self.disaster_context,
            "intentCategory": self.intent_category,
            "confidence": self.confidence,
            "matchedTerms": list(self.matched_terms),
            "capabilities": list(self.capabilities),
            "sentiment": {
                "label": self.sentiment_label,
                "score": self.sentiment_score,
                "model": self.sentiment_model,
                "status": self.sentiment_status,
            },
        }


@dataclass(frozen=True)
class BlueskyScanResult:
    query: str
    scanned_count: int
    authors: tuple[BlueskyAuthorMatch, ...]

    def as_dict(self) -> dict[str, Any]:
        sentiment_summary = {
            label: sum(
                1 for author in self.authors if author.sentiment_label == label
            )
            for label in ("positive", "neutral", "negative", "unavailable")
        }
        return {
            "query": self.query,
            "scannedCount": self.scanned_count,
            "matchCount": len(self.authors),
            "sentimentSummary": sentiment_summary,
            "authors": [author.as_dict() for author in self.authors],
        }


def _value(value: Any, key: str, default: Any = "") -> Any:
    if isinstance(value, dict):
        return value.get(key, default)
    return getattr(value, key, default)


def _post_url(uri: str) -> str:
    parts = uri.split("/")
    if (
        len(parts) != 5
        or parts[0] != "at:"
        or not parts[2]
        or parts[3] != "app.bsky.feed.post"
        or not parts[4]
    ):
        return ""
    return (
        f"https://bsky.app/profile/{quote(parts[2], safe=':')}/post/"
        f"{quote(parts[4], safe='')}"
    )


def _posted_at(value: Any) -> datetime:
    if isinstance(value, datetime):
        parsed = value
    else:
        try:
            parsed = datetime.fromisoformat(str(value or "").replace("Z", "+00:00"))
        except ValueError:
            parsed = datetime.now(timezone.utc)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


@register_adapter("bluesky")
class BlueskyAdapter(BaseAdapter):
    """Authenticated, read-only Bluesky search based on the user's notebook flow."""

    def __init__(
        self,
        client_factory: Callable[[], Any] | None = None,
        sentiment_analyzer: Any | None = None,
    ) -> None:
        self.client_factory = client_factory
        self.sentiment_analyzer = sentiment_analyzer or HuggingFaceSentimentAnalyzer(
            token=getattr(settings, "hf_token", ""),
            model=getattr(settings, "bluesky_sentiment_model", ""),
            enabled=getattr(settings, "bluesky_sentiment_enabled", False),
        )
        self.sentiment_max_posts = getattr(
            settings, "bluesky_sentiment_max_posts", 10
        )

    def _new_client(self) -> Any:
        if self.client_factory:
            return self.client_factory()
        if AtprotoClient is None:
            raise AdapterConfigurationError(
                "Bluesky scanning requires the atproto package from requirements.txt"
            )
        return AtprotoClient()

    def _scan_sync(self, query: str) -> BlueskyScanResult:
        if not settings.bluesky_email or not settings.bluesky_app_password:
            raise AdapterConfigurationError(
                "Set AAPAD_BLUESKY_EMAIL and AAPAD_BLUESKY_APP_PASSWORD on the backend"
            )

        client = self._new_client()
        try:
            client.login(settings.bluesky_email, settings.bluesky_app_password)
            response = client.app.bsky.feed.search_posts(
                params={"q": query, "limit": settings.bluesky_max_posts}
            )
        except Exception as exc:
            raise AdapterError(
                "Bluesky provider connection or search failed; verify the backend account and app password"
            ) from exc

        raw_posts = list(_value(response, "posts", []) or [])[
            : settings.bluesky_max_posts
        ]
        matches: dict[str, BlueskyAuthorMatch] = {}
        query_disaster_type = classify_hazard(query)
        confidence_rank = {"none": 0, "low": 1, "medium": 2, "high": 3}
        for post in raw_posts:
            author = _value(post, "author", None)
            record = _value(post, "record", None)
            did = str(_value(author, "did", "") or "").strip()[:220]
            handle = str(_value(author, "handle", "") or "").strip().lstrip("@")[:253]
            text = " ".join(str(_value(record, "text", "") or "").split())[:1000]
            uri = str(_value(post, "uri", "") or "").strip()[:500]
            if not did.startswith("did:") or not handle or not text or not uri:
                continue

            post_disaster_type = classify_hazard(text)
            intent = classify_help_intent(text)
            if not intent.matched:
                continue
            if post_disaster_type != "other":
                disaster_type = post_disaster_type
                disaster_context = "post"
            elif query_disaster_type != "other":
                disaster_type = query_disaster_type
                disaster_context = "query"
            else:
                continue

            candidate = BlueskyAuthorMatch(
                author_did=did,
                author_handle=handle,
                display_name=str(
                    _value(author, "display_name", "")
                    or _value(author, "displayName", "")
                    or ""
                ).strip()[:180],
                post_uri=uri,
                post_url=_post_url(uri),
                post_text=text,
                posted_at=_posted_at(
                    _value(record, "created_at", "")
                    or _value(record, "createdAt", "")
                ),
                disaster_type=disaster_type,
                disaster_context=disaster_context,
                intent_category=intent.category,
                confidence=intent.confidence,
                matched_terms=intent.matched_terms,
                capabilities=intent.capabilities,
            )
            current = matches.get(did)
            if (
                current is None
                or confidence_rank[candidate.confidence]
                > confidence_rank[current.confidence]
            ):
                matches[did] = candidate

        selected_matches = list(matches.values())
        inference_matches = selected_matches[: self.sentiment_max_posts]
        with ThreadPoolExecutor(
            max_workers=max(1, min(4, len(inference_matches)))
        ) as executor:
            sentiments = list(
                executor.map(
                    self.sentiment_analyzer.classify,
                    (match.post_text for match in inference_matches),
                )
            )

        scored_matches = [
            replace(
                match,
                sentiment_label=sentiment.label,
                sentiment_score=sentiment.score,
                sentiment_model=sentiment.model,
                sentiment_status=sentiment.status,
            )
            for match, sentiment in zip(inference_matches, sentiments, strict=True)
        ]
        scored_matches.extend(
            replace(
                match,
                sentiment_model=getattr(self.sentiment_analyzer, "model", ""),
                sentiment_status="limit_reached",
            )
            for match in selected_matches[self.sentiment_max_posts :]
        )

        return BlueskyScanResult(
            query=query,
            scanned_count=len(raw_posts),
            authors=tuple(scored_matches),
        )

    async def scan_authors(self, query: str | None = None) -> BlueskyScanResult:
        cleaned_query = " ".join((query or settings.bluesky_query).split())[:100]
        if not cleaned_query:
            cleaned_query = settings.bluesky_query
        return await asyncio.to_thread(self._scan_sync, cleaned_query)

    async def fetch(self, source: Source) -> list[IncidentCandidate]:
        if source.endpoint.rstrip("/") != BLUESKY_SERVICE:
            raise AdapterConfigurationError(
                f"Bluesky adapter source must use {BLUESKY_SERVICE}"
            )
        result = await self.scan_authors()
        incidents: list[IncidentCandidate] = []
        for author in result.authors:
            # Low-confidence and query-context leads are for human review on the
            # helper page; they must not become operational incidents implicitly.
            if author.confidence == "low" or author.disaster_context != "post":
                continue
            incident = normalize_article(
                title=f"Bluesky help offer from @{author.author_handle}",
                description=author.post_text,
                url=author.post_url,
                published_at=author.posted_at,
                source_kind="social",
                external_id=author.post_uri,
                verification_status="unverified",
            )
            if incident:
                incidents.append(incident)
        return incidents
