from __future__ import annotations

import asyncio
import io
import json
from unittest.mock import AsyncMock

import httpx
import pytest
from PIL import Image

from app.config import get_settings
from app.services import image_triage
from app.services.image_triage import (
    CaptionProviderError,
    CaptionResult,
    HuggingFaceVisionCaptionClient,
    InvalidImageError,
    OpenAIVisionCaptionClient,
    PreparedImage,
    prepare_inference_image,
    triage_assessment,
    triage_caption,
    triage_report_assessment,
)
from app.services.image_storage import ImageStorageError, StoredImage


MODEL = "Qwen/Qwen3-VL-2B-Instruct:featherless-ai"


def test_configuration_prefers_new_token_and_keeps_one_release_legacy_fallback(
    monkeypatch,
):
    monkeypatch.setenv("AAPAD_HF_TOKEN", "new-token")
    monkeypatch.setenv("AAPAD_BLIP_HF_TOKEN", "legacy-token")
    assert get_settings().hf_token == "new-token"

    monkeypatch.delenv("AAPAD_HF_TOKEN")
    assert get_settings().hf_token == "legacy-token"


def test_application_uses_openai_client_and_keeps_hugging_face_disconnected():
    import app.main as main_module

    assert isinstance(main_module.caption_client, OpenAIVisionCaptionClient)
    assert not isinstance(main_module.caption_client, HuggingFaceVisionCaptionClient)


def _assessment(
    caption: str,
    *,
    evidence: str,
    hazards: tuple[str, ...] = (),
    observations: tuple[str, ...] = (),
    model: str = "gpt-4.1-mini",
    provider: str = "openai",
) -> CaptionResult:
    return CaptionResult(
        caption=caption,
        model=model,
        provider=provider,
        evidence=evidence,
        hazards=hazards,
        observations=observations,
        prompt_version="aapad-openai-visible-disaster-v2",
    )


@pytest.mark.parametrize(
    ("caption", "decision", "hazard"),
    [
        ("a flooded street with cars submerged in water", "accepted", "flood"),
        ("a building collapsed into a pile of rubble", "accepted", "infrastructure"),
        ("a forest fire with thick smoke and flames", "accepted", "wildfire"),
        ("a dog sitting on a sofa", "rejected", "other"),
        ("a laptop on a desk", "rejected", "other"),
        ("a road beside an old building", "needs_volunteer_review", "other"),
    ],
)
def test_deterministic_caption_policy_has_three_bounded_outcomes(
    caption: str,
    decision: str,
    hazard: str,
):
    result = triage_caption(caption)

    assert result.decision == decision
    assert result.inferred_hazard == hazard
    assert result.reason


@pytest.mark.parametrize(
    ("assessment", "decision", "hazard"),
    [
        (_assessment("a flooded road", evidence="yes", hazards=("flood",)), "accepted", "flood"),
        (_assessment("a flooded road", evidence="yes", hazards=("landslide",)), "needs_volunteer_review", "other"),
        (_assessment("a flooded road", evidence="no"), "needs_volunteer_review", "other"),
        (_assessment("a dog sitting on a sofa", evidence="no"), "rejected", "other"),
        (_assessment("a vintage car is parked on a paved street", evidence="no"), "rejected", "other"),
        (_assessment("a dog sitting on a sofa", evidence="no", hazards=("flood",)), "needs_volunteer_review", "other"),
        (_assessment("a dog sitting on a sofa", evidence="unclear"), "needs_volunteer_review", "other"),
        (
            _assessment(
                "a road in a settlement",
                evidence="yes",
                hazards=("flood",),
                observations=("water covering the road",),
            ),
            "accepted",
            "flood",
        ),
    ],
)
def test_dual_check_requires_model_and_policy_agreement(
    assessment: CaptionResult,
    decision: str,
    hazard: str,
):
    result = triage_assessment(assessment)

    assert result.decision == decision
    assert result.inferred_hazard == hazard


@pytest.mark.parametrize(
    ("reported_hazard", "assessment", "decision"),
    [
        ("flood", _assessment("a flooded road", evidence="yes", hazards=("flood",)), "accepted"),
        ("landslide", _assessment("a flooded road", evidence="yes", hazards=("flood",)), "needs_volunteer_review"),
        ("flood", _assessment("a flooded road", evidence="unclear", hazards=("flood",)), "needs_volunteer_review"),
        ("flood", _assessment("a dog sitting on a sofa", evidence="no"), "needs_volunteer_review"),
    ],
)
def test_report_policy_never_auto_rejects_and_requires_reported_hazard_agreement(
    reported_hazard: str,
    assessment: CaptionResult,
    decision: str,
):
    assert triage_report_assessment(assessment, reported_hazard).decision == decision


def test_image_preprocessing_applies_orientation_resizes_and_strips_metadata():
    source = Image.new("RGB", (2000, 1000), (18, 70, 120))
    exif = Image.Exif()
    exif[274] = 6
    encoded = io.BytesIO()
    source.save(encoded, format="JPEG", exif=exif)

    prepared = prepare_inference_image(encoded.getvalue(), media_type="image/jpeg")

    assert (prepared.width, prepared.height) == (640, 1280)
    assert prepared.media_type == "image/jpeg"
    with Image.open(io.BytesIO(prepared.content)) as result:
        assert result.format == "JPEG"
        assert result.getexif() == {}


def test_image_preprocessing_converts_transparent_png_to_rgb_jpeg():
    source = Image.new("RGBA", (24, 16), (20, 30, 40, 100))
    encoded = io.BytesIO()
    source.save(encoded, format="PNG")

    prepared = prepare_inference_image(encoded.getvalue(), media_type="image/png")

    with Image.open(io.BytesIO(prepared.content)) as result:
        assert result.mode == "RGB"
        assert result.size == (24, 16)


def test_image_preprocessing_rejects_invalid_and_oversized_decoded_images(monkeypatch):
    with pytest.raises(InvalidImageError, match="decodable"):
        prepare_inference_image(b"not-an-image", media_type="image/jpeg")

    encoded = io.BytesIO()
    Image.new("RGB", (10, 10)).save(encoded, format="PNG")
    monkeypatch.setattr(image_triage, "MAX_DECODED_PIXELS", 50)
    with pytest.raises(InvalidImageError, match="dimensions"):
        prepare_inference_image(encoded.getvalue(), media_type="image/png")


def test_image_preprocessing_routes_excessive_inference_copy_to_review(monkeypatch):
    encoded = io.BytesIO()
    Image.new("RGB", (30, 30), (100, 120, 140)).save(encoded, format="PNG")
    monkeypatch.setattr(image_triage, "MAX_INFERENCE_BYTES", 10)

    with pytest.raises(CaptionProviderError, match="Prepared image"):
        prepare_inference_image(encoded.getvalue(), media_type="image/png")


def _prepared_image() -> PreparedImage:
    return PreparedImage(content=b"safe-jpeg", media_type="image/jpeg", width=10, height=10)


def _provider_response(content: str) -> httpx.Response:
    return httpx.Response(
        200,
        json={"choices": [{"message": {"content": content}}]},
    )


def _openai_provider_response(content: str) -> httpx.Response:
    return httpx.Response(
        200,
        json={
            "output": [
                {
                    "type": "message",
                    "content": [{"type": "output_text", "text": content}],
                }
            ]
        },
    )


def test_openai_client_uses_responses_vision_and_strict_structured_output():
    observed: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        observed["url"] = str(request.url)
        observed["authorization"] = request.headers.get("Authorization")
        observed["payload"] = json.loads(request.content)
        return _openai_provider_response(
            json.dumps(
                {
                    "caption": "A flooded road is visible.",
                    "disaster_evidence": "yes",
                    "hazards": ["flood"],
                    "observations": ["Water covers the road."],
                }
            )
        )

    provider = OpenAIVisionCaptionClient(
        api_key="test-openai-key",
        transport=httpx.MockTransport(handler),
    )
    result = asyncio.run(provider.caption(_prepared_image()))

    assert result.caption == "A flooded road is visible."
    assert result.provider == "openai"
    assert result.model == "gpt-4.1-mini"
    assert result.prompt_version == "aapad-openai-visible-disaster-v2"
    assert observed["url"] == "https://api.openai.com/v1/responses"
    assert observed["authorization"] == "Bearer test-openai-key"
    payload = observed["payload"]
    assert payload["store"] is False
    assert payload["text"]["format"]["strict"] is True
    assert payload["input"][0]["content"][1]["type"] == "input_image"
    assert payload["input"][0]["content"][1]["image_url"].startswith("data:image/jpeg;base64,")
    assert "test-openai-key" not in json.dumps(payload)


@pytest.mark.parametrize("status_code", [400, 401, 429, 500])
def test_openai_client_returns_secret_safe_errors(status_code: int, capsys):
    secret = "sk-test-do-not-leak"
    provider = OpenAIVisionCaptionClient(
        api_key=secret,
        transport=httpx.MockTransport(
            lambda _: httpx.Response(status_code, text=f"provider body {secret}")
        ),
    )

    with pytest.raises(CaptionProviderError) as caught:
        asyncio.run(provider.caption(_prepared_image()))

    assert secret not in str(caught.value)
    captured = capsys.readouterr()
    assert secret not in captured.out
    assert secret not in captured.err


def test_hf_client_sends_fixed_router_payload_and_parses_structured_evidence():
    observed: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        observed["url"] = str(request.url)
        observed["authorization"] = request.headers.get("Authorization")
        observed["payload"] = json.loads(request.content)
        return _provider_response(
            json.dumps(
                {
                    "caption": " A flooded   street with submerged cars. ",
                    "disaster_evidence": "yes",
                    "hazards": ["flood"],
                    "observations": ["Water covers the road."],
                }
            )
        )

    provider = HuggingFaceVisionCaptionClient(
        hf_token="test-token",
        transport=httpx.MockTransport(handler),
    )
    result = asyncio.run(provider.caption(_prepared_image()))

    assert result.caption == "A flooded street with submerged cars."
    assert result.evidence == "yes"
    assert result.hazards == ("flood",)
    assert result.provider == "huggingface:featherless-ai"
    assert observed["url"] == "https://router.huggingface.co/v1/chat/completions"
    assert observed["authorization"] == "Bearer test-token"
    payload = observed["payload"]
    assert payload["model"] == MODEL
    assert payload["temperature"] == 0
    assert payload["stream"] is False
    image_url = payload["messages"][0]["content"][1]["image_url"]["url"]
    assert image_url.startswith("data:image/jpeg;base64,")
    assert "test-token" not in json.dumps(payload)


def test_hf_client_accepts_one_json_code_fence():
    content = """```json
    {"caption":"a dog sitting on a sofa","disaster_evidence":"no","hazards":[],"observations":["A dog is indoors."]}
    ```"""
    provider = HuggingFaceVisionCaptionClient(
        hf_token="token",
        transport=httpx.MockTransport(lambda _: _provider_response(content)),
    )

    result = asyncio.run(provider.caption(_prepared_image()))

    assert result.evidence == "no"
    assert result.hazards == ()


@pytest.mark.parametrize(
    "content",
    [
        "not json",
        "{}",
        '{"caption":"scene","disaster_evidence":"maybe","hazards":[],"observations":[]}',
        '{"caption":"scene","disaster_evidence":"yes","hazards":["fire"],"observations":[]}',
        json.dumps(
            {
                "caption": "x" * 501,
                "disaster_evidence": "unclear",
                "hazards": [],
                "observations": [],
            }
        ),
    ],
)
def test_hf_client_rejects_malformed_or_unbounded_model_output(content: str):
    provider = HuggingFaceVisionCaptionClient(
        hf_token="token",
        transport=httpx.MockTransport(lambda _: _provider_response(content)),
    )

    with pytest.raises(CaptionProviderError):
        asyncio.run(provider.caption(_prepared_image()))


@pytest.mark.parametrize("status_code", [400, 401, 402, 403, 429, 500, 503])
def test_hf_client_converts_http_failures_to_secret_safe_provider_error(
    status_code: int,
    capsys,
):
    secret = "hf-do-not-leak-this-token"
    provider = HuggingFaceVisionCaptionClient(
        hf_token=secret,
        transport=httpx.MockTransport(
            lambda _: httpx.Response(status_code, text=f"provider body {secret}")
        ),
    )

    with pytest.raises(CaptionProviderError) as caught:
        asyncio.run(provider.caption(_prepared_image()))

    assert secret not in str(caught.value)
    captured = capsys.readouterr()
    assert secret not in captured.out
    assert secret not in captured.err


def test_hf_client_converts_timeout_to_provider_error():
    def timeout(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("timed out", request=request)

    provider = HuggingFaceVisionCaptionClient(
        hf_token="token",
        transport=httpx.MockTransport(timeout),
    )

    with pytest.raises(CaptionProviderError, match="unavailable"):
        asyncio.run(provider.caption(_prepared_image()))


def test_hf_client_never_calls_network_without_token():
    called = False

    def handler(_: httpx.Request) -> httpx.Response:
        nonlocal called
        called = True
        return _provider_response("{}")

    provider = HuggingFaceVisionCaptionClient(
        hf_token="",
        transport=httpx.MockTransport(handler),
    )

    with pytest.raises(CaptionProviderError, match="not configured"):
        asyncio.run(provider.caption(_prepared_image()))
    assert called is False


def test_hf_client_enforces_process_local_hourly_call_limit():
    content = json.dumps(
        {
            "caption": "a road beside a building",
            "disaster_evidence": "unclear",
            "hazards": [],
            "observations": [],
        }
    )
    calls = 0

    def handler(_: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return _provider_response(content)

    provider = HuggingFaceVisionCaptionClient(
        hf_token="token",
        max_calls_per_hour=1,
        transport=httpx.MockTransport(handler),
    )

    async def scenario() -> None:
        await provider.caption(_prepared_image())
        with pytest.raises(CaptionProviderError, match="call limit"):
            await provider.caption(_prepared_image())

    asyncio.run(scenario())
    assert calls == 1


def _submit_report(
    client,
    image_bytes: bytes,
    *,
    location: str,
    disaster_type: str = "flood",
):
    return client.post(
        "/api/reports",
        data={
            "description": "Recent visible damage is affecting access to nearby homes.",
            "disaster_type": disaster_type,
            "severity": "5",
            "latitude": "26.14",
            "longitude": "91.73",
            "location_name": location,
            "needs": '["rescue", "shelter"]',
            "reporter_name": "Vision test reporter",
            "contact": "vision-test@example.org",
            "consent": "true",
        },
        files={"image": ("evidence.jpg", image_bytes, "image/jpeg")},
    )


def test_matching_disaster_checks_activate_ai_screened_incident_and_store_audit(
    client,
    valid_jpeg_bytes,
    monkeypatch,
):
    import app.main as main_module

    monkeypatch.setattr(
        main_module.image_store,
        "upload",
        AsyncMock(
            return_value=StoredImage(
                public_id="aapad-snehi/reports/test",
                asset_id="asset-test",
                format="jpg",
            )
        ),
    )

    monkeypatch.setattr(
        main_module.caption_client,
        "caption",
        AsyncMock(
            return_value=_assessment(
                "a flooded street with cars submerged in water",
                evidence="yes",
                hazards=("flood",),
                observations=("Water covers the road.",),
            )
        ),
    )

    response = _submit_report(
        client,
        valid_jpeg_bytes,
        location="OpenAI accepted, Assam",
    )

    assert response.status_code == 201, response.text
    payload = response.json()
    assert payload["moderationStatus"] == "accepted"
    assert payload["incident"]["active"] is True
    assert payload["incident"]["verificationStatus"] == "ai_screened"
    assert payload["incident"]["disasterType"] == "flood"
    dashboard_ids = {
        item["id"] for item in client.get("/api/dashboard").json()["priorityIncidents"]
    }
    task_ids = {item["id"] for item in client.get("/api/tasks/open").json()}
    assert payload["incident"]["id"] in dashboard_ids
    assert payload["incident"]["id"] in task_ids

    stored = next(
        item
        for item in client.get("/api/reports").json()
        if item["trackingId"] == payload["trackingId"]
    )
    assert stored["aiModel"] == "gpt-4.1-mini"
    assert stored["aiProvider"] == "openai"
    assert stored["aiPromptVersion"] == "aapad-openai-visible-disaster-v2"
    assert stored["aiAnalysis"] == {
        "disasterEvidence": "yes",
        "hazards": ["flood"],
        "observations": ["Water covers the road."],
    }


def test_non_disaster_assessment_routes_to_volunteer_review_and_keeps_incident_private(
    client,
    valid_jpeg_bytes,
    monkeypatch,
):
    import app.main as main_module

    monkeypatch.setattr(
        main_module.caption_client,
        "caption",
        AsyncMock(return_value=_assessment("a dog sitting on a sofa", evidence="no")),
    )
    response = _submit_report(
        client,
        valid_jpeg_bytes,
        location="OpenAI review, Assam",
    )

    assert response.status_code == 201, response.text
    payload = response.json()
    assert payload["moderationStatus"] == "needs_volunteer_review"
    assert payload["incident"]["active"] is False
    active_ids = {item["id"] for item in client.get("/api/incidents?days=1").json()}
    assert payload["incident"]["id"] not in active_ids


def test_unclear_assessment_waits_for_review_then_supports_manual_decision(
    client,
    valid_jpeg_bytes,
    monkeypatch,
):
    import app.main as main_module

    monkeypatch.setattr(
        main_module.caption_client,
        "caption",
        AsyncMock(
            return_value=_assessment(
                "a road beside an old building",
                evidence="unclear",
            )
        ),
    )
    created = _submit_report(
        client,
        valid_jpeg_bytes,
        location="OpenAI review decision, Assam",
    ).json()

    assert created["moderationStatus"] == "needs_volunteer_review"
    assert created["incident"]["active"] is False

    approved = client.patch(
        f"/api/reports/{created['trackingId']}/moderation",
        json={"decision": "approve", "reviewer_name": "Verified Volunteer"},
    )
    assert approved.status_code == 200, approved.text
    assert approved.json()["moderationStatus"] == "community_approved"
    assert approved.json()["incident"]["active"] is True
    assert approved.json()["incident"]["verificationStatus"] == "community_reviewed"

    second = _submit_report(
        client,
        valid_jpeg_bytes,
        location="OpenAI rejected by volunteer, Assam",
    ).json()
    assert client.get(f"/api/reports/{second['trackingId']}/image").status_code == 200
    rejected = client.patch(
        f"/api/reports/{second['trackingId']}/moderation",
        json={"decision": "reject", "reviewer_name": "Verified Volunteer"},
    )
    assert rejected.status_code == 200, rejected.text
    assert rejected.json()["moderationStatus"] == "rejected"
    assert rejected.json()["incident"]["active"] is False
    assert rejected.json()["imageAvailable"] is False
    assert client.get(f"/api/reports/{second['trackingId']}/image").status_code == 404


def test_provider_or_preparation_failure_never_auto_rejects_and_report_is_preserved(
    client,
    valid_jpeg_bytes,
    monkeypatch,
):

    import app.main as main_module

    caption_mock = AsyncMock(side_effect=CaptionProviderError("provider unavailable"))
    monkeypatch.setattr(main_module.caption_client, "caption", caption_mock)
    provider_failure = _submit_report(
        client,
        valid_jpeg_bytes,
        location="Provider unavailable, Assam",
    ).json()
    assert provider_failure["moderationStatus"] == "needs_volunteer_review"
    assert provider_failure["caption"] == ""
    assert provider_failure["incident"]["active"] is False

    monkeypatch.setattr(
        main_module,
        "prepare_inference_image",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            CaptionProviderError("prepared image is too large")
        ),
    )
    preparation_failure = _submit_report(
        client,
        valid_jpeg_bytes,
        location="Prepared image held, Assam",
    ).json()
    assert preparation_failure["moderationStatus"] == "needs_volunteer_review"
    assert preparation_failure["incident"]["active"] is False
    report_ids = {item["trackingId"] for item in client.get("/api/reports").json()}
    assert preparation_failure["trackingId"] in report_ids


def test_volunteer_rejection_deletes_cloudinary_image_before_saving_state(
    client,
    valid_jpeg_bytes,
    monkeypatch,
):
    import app.main as main_module

    monkeypatch.setattr(
        main_module.caption_client,
        "caption",
        AsyncMock(return_value=_assessment("a road beside a building", evidence="unclear")),
    )
    monkeypatch.setattr(
        main_module.image_store,
        "upload",
        AsyncMock(
            return_value=StoredImage(
                public_id="aapad-snehi/reports/cloud-reject",
                asset_id="asset-cloud-reject",
                format="jpg",
            )
        ),
    )
    delete = AsyncMock(return_value=None)
    monkeypatch.setattr(main_module.image_store, "delete", delete)
    created = _submit_report(
        client,
        valid_jpeg_bytes,
        location="Cloud rejection, Assam",
    ).json()

    rejected = client.patch(
        f"/api/reports/{created['trackingId']}/moderation",
        json={"decision": "reject", "reviewer_name": "Volunteer reviewer"},
    )

    assert rejected.status_code == 200, rejected.text
    assert rejected.json()["moderationStatus"] == "rejected"
    assert rejected.json()["imageAvailable"] is False
    delete.assert_awaited_once_with("aapad-snehi/reports/cloud-reject")


def test_cloudinary_delete_failure_does_not_commit_rejection(
    client,
    valid_jpeg_bytes,
    monkeypatch,
):
    import app.main as main_module

    monkeypatch.setattr(
        main_module.caption_client,
        "caption",
        AsyncMock(return_value=_assessment("an unclear road scene", evidence="unclear")),
    )
    monkeypatch.setattr(
        main_module.image_store,
        "upload",
        AsyncMock(
            return_value=StoredImage(
                public_id="aapad-snehi/reports/cloud-delete-failure",
                asset_id="asset-cloud-delete-failure",
                format="jpg",
            )
        ),
    )
    monkeypatch.setattr(
        main_module.image_store,
        "delete",
        AsyncMock(side_effect=ImageStorageError("secret-safe failure")),
    )
    created = _submit_report(
        client,
        valid_jpeg_bytes,
        location="Cloud delete failure, Assam",
    ).json()

    rejected = client.patch(
        f"/api/reports/{created['trackingId']}/moderation",
        json={"decision": "reject", "reviewer_name": "Volunteer reviewer"},
    )

    assert rejected.status_code == 502
    stored = next(
        item for item in client.get("/api/reports").json()
        if item["trackingId"] == created["trackingId"]
    )
    assert stored["moderationStatus"] == "needs_volunteer_review"
    assert stored["imageAvailable"] is True


def test_invalid_decoded_image_is_rejected_as_input_before_provider_call(client, monkeypatch):
    import app.main as main_module

    caption_mock = AsyncMock()
    monkeypatch.setattr(main_module.caption_client, "caption", caption_mock)
    response = _submit_report(
        client,
        b"\xff\xd8\xffnot-a-real-jpeg",
        location="Invalid evidence, Assam",
    )

    assert response.status_code == 415
    caption_mock.assert_not_awaited()
