from types import SimpleNamespace

from app.services.sentiment import (
    HuggingFaceSentimentAnalyzer,
    preprocess_social_text,
)


class FakeInferenceClient:
    def __init__(self, outputs=None, error: Exception | None = None):
        self.outputs = outputs or []
        self.error = error
        self.calls = []

    def text_classification(self, text, *, model, top_k):
        self.calls.append((text, model, top_k))
        if self.error:
            raise self.error
        return self.outputs


def test_social_text_preprocessing_replaces_handles_and_links():
    assert preprocess_social_text(
        "Thanks @helper.example — details at https://example.org/a"
    ) == "Thanks @user — details at http"


def test_sentiment_selects_highest_supported_label():
    client = FakeInferenceClient(
        [
            SimpleNamespace(label="neutral", score=0.25),
            SimpleNamespace(label="positive", score=0.70),
            SimpleNamespace(label="negative", score=0.05),
        ]
    )
    analyzer = HuggingFaceSentimentAnalyzer(
        token="test-token",
        model="test-model",
        client=client,
    )

    result = analyzer.classify("We are providing food and shelter.")

    assert result.label == "positive"
    assert result.score == 0.70
    assert result.status == "available"
    assert client.calls == [("We are providing food and shelter.", "test-model", 3)]


def test_sentiment_is_truthfully_unavailable_without_configuration():
    result = HuggingFaceSentimentAnalyzer(token="").classify("A public post")

    assert result.label == "unavailable"
    assert result.score is None
    assert result.status == "needs_config"


def test_provider_error_is_secret_safe_and_opens_circuit_breaker():
    client = FakeInferenceClient(error=RuntimeError("secret-token leaked"))
    analyzer = HuggingFaceSentimentAnalyzer(token="secret-token", client=client)

    first = analyzer.classify("first")
    second = analyzer.classify("second")

    assert first.status == "provider_error"
    assert second.status == "provider_error"
    assert len(client.calls) == 1
