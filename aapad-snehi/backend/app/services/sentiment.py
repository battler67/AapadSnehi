from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any


DEFAULT_SENTIMENT_MODEL = "cardiffnlp/twitter-roberta-base-sentiment-latest"
SENTIMENT_LABELS = {"negative", "neutral", "positive"}


@dataclass(frozen=True)
class SentimentResult:
    label: str
    score: float | None
    model: str
    status: str


def preprocess_social_text(text: str) -> str:
    """Apply the model card's lightweight username/link normalization."""

    normalized = " ".join(text.split())[:2000]
    normalized = re.sub(r"(?<!\w)@[A-Za-z0-9._:-]+", "@user", normalized)
    normalized = re.sub(r"https?://\S+|www\.\S+", "http", normalized)
    return normalized


class HuggingFaceSentimentAnalyzer:
    def __init__(
        self,
        *,
        token: str,
        model: str = DEFAULT_SENTIMENT_MODEL,
        enabled: bool = True,
        client: Any | None = None,
    ) -> None:
        self.token = token
        self.model = model or DEFAULT_SENTIMENT_MODEL
        self.enabled = enabled
        self._client = client
        self._provider_failed = False

    def _get_client(self) -> Any:
        if self._client is not None:
            return self._client
        from huggingface_hub import InferenceClient

        self._client = InferenceClient(
            provider="hf-inference",
            api_key=self.token,
            timeout=12,
        )
        return self._client

    def classify(self, text: str) -> SentimentResult:
        if not self.enabled:
            return SentimentResult("unavailable", None, self.model, "disabled")
        if not self.token:
            return SentimentResult("unavailable", None, self.model, "needs_config")
        if self._provider_failed:
            return SentimentResult("unavailable", None, self.model, "provider_error")

        try:
            outputs = self._get_client().text_classification(
                preprocess_social_text(text),
                model=self.model,
                top_k=3,
            )
            choices = list(outputs or [])
            if choices and isinstance(choices[0], list):
                choices = list(choices[0])
            parsed: list[tuple[str, float]] = []
            for item in choices:
                raw_label = (
                    item.get("label", "")
                    if isinstance(item, dict)
                    else getattr(item, "label", "")
                )
                raw_score = (
                    item.get("score", 0.0)
                    if isinstance(item, dict)
                    else getattr(item, "score", 0.0)
                )
                label = str(raw_label).strip().lower()
                if label in SENTIMENT_LABELS:
                    parsed.append((label, float(raw_score)))
            if not parsed:
                return SentimentResult("unavailable", None, self.model, "invalid_response")
            label, score = max(parsed, key=lambda item: item[1])
            return SentimentResult(label, max(0.0, min(1.0, score)), self.model, "available")
        except Exception:
            # Provider errors are intentionally secret-safe and do not block a scan.
            self._provider_failed = True
            return SentimentResult("unavailable", None, self.model, "provider_error")
