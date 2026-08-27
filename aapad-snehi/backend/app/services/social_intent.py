from __future__ import annotations

import re
from dataclasses import dataclass


POLICY_VERSION = "bluesky-help-keywords-v1"


@dataclass(frozen=True)
class HelpIntent:
    matched: bool
    matched_terms: tuple[str, ...]
    capabilities: tuple[str, ...]


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

_REQUEST_OR_NEGATION_PATTERNS = tuple(
    re.compile(pattern, re.IGNORECASE)
    for pattern in (
        r"\b(?:please|pls)\s+(?:send\s+)?help\b",
        r"\b(?:i|we)\s+need\s+(?:urgent\s+)?help\b",
        r"\b(?:need|require|seeking)\s+(?:food|water|shelter|rescue|medical|transport|volunteers?)\b",
        r"\b(?:cannot|can't|cant|won't|not able|unable|not available)\s+(?:to\s+)?(?:help|assist|volunteer|provide)?\b",
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
    if any(pattern.search(normalized) for pattern in _REQUEST_OR_NEGATION_PATTERNS):
        return HelpIntent(matched=False, matched_terms=(), capabilities=())

    matched_terms = tuple(
        label for label, pattern in _OFFER_PATTERNS if pattern.search(normalized)
    )
    capabilities = tuple(
        name for name, pattern in _CAPABILITY_PATTERNS if pattern.search(normalized)
    )
    return HelpIntent(
        matched=bool(matched_terms),
        matched_terms=matched_terms,
        capabilities=capabilities,
    )
