from __future__ import annotations

import re
from dataclasses import dataclass


POLICY_VERSION = "bluesky-help-keywords-v2"


@dataclass(frozen=True)
class HelpIntent:
    matched: bool
    matched_terms: tuple[str, ...]
    capabilities: tuple[str, ...]
    category: str
    confidence: str


_OFFER_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = tuple(
    (label, re.compile(pattern, re.IGNORECASE))
    for label, pattern in (
        (
            "can help",
            r"\b(?:i|we|our team|our group)\s+(?:can|will|are ready to|are able to|are available to)\s+(?:help|assist|volunteer|provide|deliver|donate|rescue|transport)",
        ),
        (
            "willing to help",
            r"\b(?:available|ready|willing)\s+to\s+(?:help|assist|volunteer|provide|deliver|donate|rescue|transport)",
        ),
        (
            "offering support",
            r"\b(?:offering|providing|distributing|donating)\s+(?:free\s+)?(?:help|support|food|water|shelter|transport|medical|supplies|meals)",
        ),
        (
            "resources available",
            r"\b(?:volunteers?|doctors?|nurses?|drivers?|boats?|ambulances?|shelters?|supplies?|meals?|food|water)\s+(?:is\s+|are\s+)?available\b",
        ),
        (
            "contact for help",
            r"\bcontact\s+(?:me|us)\s+(?:for|if you need)\b",
        ),
    )
)

_REQUEST_PATTERNS = tuple(
    re.compile(pattern, re.IGNORECASE)
    for pattern in (
        r"\b(?:please|pls)\s+(?:send\s+)?help\b",
        r"\b(?:i|we)\s+need\s+(?:urgent\s+)?help\b",
        r"\b(?:need|require|seeking)\s+(?:food|water|shelter|rescue|medical|transport|volunteers?)\b",
    )
)


_NEGATION_PATTERNS = tuple(
    re.compile(pattern, re.IGNORECASE)
    for pattern in (
        r"\b(?:cannot|can't|cant|won't|not able|unable|not available)\s+(?:to\s+)?(?:help|assist|volunteer|provide)?\b",
    )
)


_ACTIVE_ASSISTANCE_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = tuple(
    (label, re.compile(pattern, re.IGNORECASE))
    for label, pattern in (
        (
            "active aid delivery",
            r"\b(?:we|our (?:team|staff|experts?|colleagues?|partners?))\s+(?:are\s+|have\s+|have been\s+|were\s+)?(?:providing|delivering|distributing|running|operating|deploying|supporting|assisting|helping)\b",
        ),
        (
            "aid delivered",
            r"\b(?:we|our (?:team|staff|colleagues?|partners?))\s+(?:have\s+|has\s+)?(?:delivered|distributed|provided|opened|deployed)\b",
        ),
        (
            "response work underway",
            r"\b(?:we|our (?:team|staff|colleagues?|partners?))\s+(?:are\s+|have been\s+)?working\s+(?:in|with|to|on)\b",
        ),
    )
)


_INSTITUTIONAL_SUPPORT_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = tuple(
    (label, re.compile(pattern, re.IGNORECASE))
    for label, pattern in (
        (
            "institutional support offered",
            r"\b(?:government|country|agency|organisation|organization|foundation|community|team|group|company|we)\s+(?:has\s+|have\s+)?(?:offers?|offered|pledges?|pledged)\b.{0,80}\b(?:aid|assistance|help|relief|support)\b",
        ),
        (
            "support offered",
            r"\b(?:offers?|offered|pledges?|pledged)\b.{0,80}\b(?:aid|assistance|help|relief|support)\b",
        ),
    )
)


_FUNDRAISING_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = tuple(
    (label, re.compile(pattern, re.IGNORECASE))
    for label, pattern in (
        (
            "donation or fundraiser",
            r"\b(?:donat(?:e|es|ed|ing|ion|ions)|fundrais(?:e|es|ed|er|ers|ing)|charity|relief fund)\b",
        ),
        (
            "relief appeal",
            r"\b(?:appeal|campaign|fund)\b.{0,80}\b(?:aid|assistance|disaster|flood|relief|recovery|support|victims?)\b",
        ),
        (
            "support affected people",
            r"\bsupport(?:ing)?\b.{0,80}\b(?:affected|families|people|residents|survivors|victims)\b",
        ),
    )
)

_CAPABILITY_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = tuple(
    (name, re.compile(pattern, re.IGNORECASE))
    for name, pattern in (
        ("food", r"\b(?:food|meal|meals|ration|rations)\b"),
        ("water", r"\b(?:water|drinking water)\b"),
        ("shelter", r"\b(?:shelter|accommodation|beds?|stay)\b"),
        ("medical", r"\b(?:medical|doctor|nurse|ambulance|first aid|medicine)\b"),
        ("rescue", r"\b(?:rescue|boats?|evacuat(?:e|ion))\b"),
        ("transport", r"\b(?:transport|vehicle|driver|car|truck)\b"),
        ("supplies", r"\b(?:donat(?:e|ing|ion)|supplies|funds?)\b"),
        ("volunteering", r"\b(?:volunteers?|help|assist|support)\b"),
    )
)


def classify_help_intent(text: str) -> HelpIntent:
    """Return a conservative keyword decision; this is not ML or sentiment analysis."""

    normalized = " ".join(text.split())[:4000]
    if any(pattern.search(normalized) for pattern in _NEGATION_PATTERNS):
        return HelpIntent(
            matched=False,
            matched_terms=(),
            capabilities=(),
            category="rejected_negation",
            confidence="none",
        )

    explicit_terms = tuple(
        label for label, pattern in _OFFER_PATTERNS if pattern.search(normalized)
    )
    active_terms = tuple(
        label
        for label, pattern in _ACTIVE_ASSISTANCE_PATTERNS
        if pattern.search(normalized)
    )
    institutional_terms = tuple(
        label
        for label, pattern in _INSTITUTIONAL_SUPPORT_PATTERNS
        if pattern.search(normalized)
    )
    fundraising_terms = tuple(
        label
        for label, pattern in _FUNDRAISING_PATTERNS
        if pattern.search(normalized)
    )
    all_positive_terms = (
        explicit_terms + active_terms + institutional_terms + fundraising_terms
    )
    if any(pattern.search(normalized) for pattern in _REQUEST_PATTERNS) and not all_positive_terms:
        return HelpIntent(
            matched=False,
            matched_terms=(),
            capabilities=(),
            category="request_for_help",
            confidence="none",
        )

    if explicit_terms:
        category, confidence = "explicit_offer", "high"
    elif active_terms:
        category, confidence = "active_assistance", "medium"
    elif institutional_terms:
        category, confidence = "institutional_support", "medium"
    elif fundraising_terms:
        category, confidence = "fundraising_or_donation", "low"
    else:
        category, confidence = "no_assistance_signal", "none"

    capabilities = tuple(
        name for name, pattern in _CAPABILITY_PATTERNS if pattern.search(normalized)
    )
    return HelpIntent(
        matched=bool(all_positive_terms),
        matched_terms=all_positive_terms,
        capabilities=capabilities,
        category=category,
        confidence=confidence,
    )
