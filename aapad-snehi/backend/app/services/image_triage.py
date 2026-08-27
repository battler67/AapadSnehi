from __future__ import annotations

import asyncio
import base64
import io
import json
import re
import time
import warnings
from collections import deque
from dataclasses import dataclass
from typing import Callable

import httpx
from PIL import Image, ImageOps, UnidentifiedImageError

from .normalizer import HAZARD_KEYWORDS, classify_hazard


HF_CHAT_COMPLETIONS_URL = "https://router.huggingface.co/v1/chat/completions"
OPENAI_RESPONSES_URL = "https://api.openai.com/v1/responses"
DEFAULT_CAPTION_MODEL = "Qwen/Qwen3-VL-2B-Instruct:featherless-ai"
PROMPT_VERSION = "aapad-visible-disaster-v1"
OPENAI_PROMPT_VERSION = "aapad-openai-visible-disaster-v2"
MAX_CAPTION_CHARS = 500
MAX_OBSERVATION_CHARS = 160
MAX_OBSERVATIONS = 8
MAX_HAZARDS = 5
MAX_DECODED_PIXELS = 20_000_000
MAX_INFERENCE_EDGE = 1280
MAX_INFERENCE_BYTES = 2 * 1024 * 1024
CANONICAL_HAZARDS = frozenset(HAZARD_KEYWORDS)


class CaptionProviderError(RuntimeError):
    """A remote or prepared-image failure that must route to human review."""


class InvalidImageError(ValueError):
    """An invalid or unsafe image that should be rejected as request input."""


@dataclass(frozen=True)
class PreparedImage:
    content: bytes
    media_type: str
    width: int
    height: int


@dataclass(frozen=True)
class CaptionResult:
    caption: str
    model: str
    provider: str
    evidence: str
    hazards: tuple[str, ...]
    observations: tuple[str, ...]
    prompt_version: str = PROMPT_VERSION

    def analysis_dict(self) -> dict[str, object]:
        return {
            "disasterEvidence": self.evidence,
            "hazards": list(self.hazards),
            "observations": list(self.observations),
        }


@dataclass(frozen=True)
class TriageResult:
    decision: str
    reason: str
    inferred_hazard: str


VISIBLE_DISASTER_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    (
        "flood",
        re.compile(
            r"\b(flooded|submerged|overflowing|street(?:s)? (?:full of|covered (?:in|with)) water|water covering (?:(?:a|the) )?(?:road|street|house))\b",
            re.IGNORECASE,
        ),
    ),
    (
        "wildfire",
        re.compile(
            r"\b(flames?|wildfire|forest fire|(?:house|building|forest|vehicle) (?:is )?(?:burning|on fire)|thick smoke)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "infrastructure",
        re.compile(
            r"\b(collapsed|rubble|wreckage|destroyed (?:house|building|bridge)|damaged (?:house|building|bridge|road)|cracked building)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "landslide",
        re.compile(
            r"\b(landslide|mudslide|rockfall|rocks? (?:covering|blocking) (?:a )?road|mud (?:covering|blocking) (?:a )?road|debris blocking (?:a )?road)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "storm",
        re.compile(
            r"\b(tornado|storm damage|fallen trees?|trees? fallen (?:on|across) (?:a )?road|roof (?:blown off|torn off))\b",
            re.IGNORECASE,
        ),
    ),
)

CLEAR_ORDINARY_PATTERNS: tuple[re.Pattern[str], ...] = tuple(
    re.compile(pattern, re.IGNORECASE)
    for pattern in (
        r"\b(?:selfie|portrait)\b",
        r"\b(?:plate|bowl) of food\b",
        r"\b(?:cat|dog|bird) (?:sitting|lying|playing|standing)\b",
        r"\b(?:laptop|computer|keyboard) on (?:a )?(?:desk|table)\b",
        r"\b(?:bedroom|living room|kitchen) with\b",
        r"\b(?:wedding|birthday party|baseball game|football game)\b",
        r"\b(?:car|bus|motorcycle) (?:is )?parked\b",
        r"\b(?:flowers?|sunset) (?:in|over|on)\b",
    )
)


def _normalized_text(value: object) -> str:
    return " ".join(str(value or "").split()).strip()


def prepare_inference_image(content: bytes, *, media_type: str) -> PreparedImage:
    if media_type not in {"image/jpeg", "image/jpg", "image/png", "image/webp"}:
        raise InvalidImageError("Only valid JPEG, PNG, or WebP images are accepted")
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(content)) as source:
                width, height = source.size
                if width <= 0 or height <= 0 or width * height > MAX_DECODED_PIXELS:
                    raise InvalidImageError("Image dimensions exceed the safe processing limit")
                source.load()
                transposed = ImageOps.exif_transpose(source)
                image = transposed.convert("RGB")
    except InvalidImageError:
        raise
    except (
        Image.DecompressionBombError,
        Image.DecompressionBombWarning,
        UnidentifiedImageError,
        OSError,
        ValueError,
    ) as exc:
        raise InvalidImageError("The uploaded file is not a decodable safe image") from exc

    image.thumbnail((MAX_INFERENCE_EDGE, MAX_INFERENCE_EDGE), Image.Resampling.LANCZOS)
    encoded = io.BytesIO()
    image.save(encoded, format="JPEG", quality=85, optimize=True)
    inference_bytes = encoded.getvalue()
    if len(inference_bytes) > MAX_INFERENCE_BYTES:
        encoded = io.BytesIO()
        image.save(encoded, format="JPEG", quality=75, optimize=True)
        inference_bytes = encoded.getvalue()
    if len(inference_bytes) > MAX_INFERENCE_BYTES:
        raise CaptionProviderError("Prepared image exceeds the hosted screening limit")
    return PreparedImage(
        content=inference_bytes,
        media_type="image/jpeg",
        width=image.width,
        height=image.height,
    )


class RollingHourlyLimiter:
    def __init__(
        self,
        max_calls: int,
        *,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.max_calls = max(0, max_calls)
        self._clock = clock
        self._calls: deque[float] = deque()
        self._lock = asyncio.Lock()

    async def acquire(self) -> bool:
        async with self._lock:
            now = self._clock()
            cutoff = now - 3600
            while self._calls and self._calls[0] <= cutoff:
                self._calls.popleft()
            if self.max_calls == 0 or len(self._calls) >= self.max_calls:
                return False
            self._calls.append(now)
            return True


class HuggingFaceVisionCaptionClient:
    def __init__(
        self,
        *,
        hf_token: str,
        model: str = DEFAULT_CAPTION_MODEL,
        timeout_seconds: float = 45.0,
        max_calls_per_hour: int = 20,
        max_concurrency: int = 2,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.hf_token = hf_token
        self.model = model
        self.timeout_seconds = timeout_seconds
        self._limiter = RollingHourlyLimiter(max_calls_per_hour)
        self._semaphore = asyncio.Semaphore(max(1, max_concurrency))
        self._transport = transport

    async def caption(self, image: PreparedImage) -> CaptionResult:
        if not self.hf_token:
            raise CaptionProviderError("Hosted image screening is not configured")
        if not await self._limiter.acquire():
            raise CaptionProviderError("Hosted image screening call limit was reached")

        data_url = (
            f"data:{image.media_type};base64,"
            f"{base64.b64encode(image.content).decode('ascii')}"
        )
        payload = {
            "model": self.model,
            "temperature": 0,
            "max_tokens": 180,
            "stream": False,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": _screening_prompt()},
                        {"type": "image_url", "image_url": {"url": data_url}},
                    ],
                }
            ],
        }
        headers = {
            "Authorization": f"Bearer {self.hf_token}",
            "Content-Type": "application/json",
        }
        try:
            async with self._semaphore:
                async with httpx.AsyncClient(
                    timeout=self.timeout_seconds,
                    transport=self._transport,
                ) as client:
                    response = await client.post(
                        HF_CHAT_COMPLETIONS_URL,
                        headers=headers,
                        json=payload,
                    )
        except (httpx.TimeoutException, httpx.HTTPError) as exc:
            raise CaptionProviderError("Hosted image screening is unavailable") from exc
        if response.status_code != 200:
            raise CaptionProviderError("Hosted image screening is unavailable")
        try:
            envelope = response.json()
            content = envelope["choices"][0]["message"]["content"]
        except (ValueError, KeyError, IndexError, TypeError) as exc:
            raise CaptionProviderError("Hosted image screening returned an invalid response") from exc
        result = _parse_model_content(content)
        return CaptionResult(
            caption=result["caption"],
            model=self.model[:180],
            provider=_provider_name(self.model),
            evidence=result["disaster_evidence"],
            hazards=tuple(result["hazards"]),
            observations=tuple(result["observations"]),
        )


class OpenAIVisionCaptionClient:
    """Bounded OpenAI Responses vision client used by the active report flow."""

    def __init__(
        self,
        *,
        api_key: str,
        model: str = "gpt-4.1-mini",
        timeout_seconds: float = 45.0,
        max_calls_per_hour: int = 20,
        max_concurrency: int = 2,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.api_key = api_key
        self.model = model
        self.timeout_seconds = timeout_seconds
        self._limiter = RollingHourlyLimiter(max_calls_per_hour)
        self._semaphore = asyncio.Semaphore(max(1, max_concurrency))
        self._transport = transport

    async def caption(self, image: PreparedImage) -> CaptionResult:
        if not self.api_key:
            raise CaptionProviderError("OpenAI image screening is not configured")
        if not await self._limiter.acquire():
            raise CaptionProviderError("OpenAI image screening call limit was reached")

        data_url = (
            f"data:{image.media_type};base64,"
            f"{base64.b64encode(image.content).decode('ascii')}"
        )
        hazards = sorted(CANONICAL_HAZARDS)
        payload = {
            "model": self.model,
            "store": False,
            "temperature": 0,
            "max_output_tokens": 220,
            "input": [
                {
                    "role": "user",
                    "content": [
                        {"type": "input_text", "text": _screening_prompt()},
                        {
                            "type": "input_image",
                            "image_url": data_url,
                            "detail": "low",
                        },
                    ],
                }
            ],
            "text": {
                "format": {
                    "type": "json_schema",
                    "name": "disaster_image_assessment",
                    "strict": True,
                    "schema": {
                        "type": "object",
                        "additionalProperties": False,
                        "properties": {
                            "caption": {"type": "string"},
                            "disaster_evidence": {
                                "type": "string",
                                "enum": ["yes", "no", "unclear"],
                            },
                            "hazards": {
                                "type": "array",
                                "items": {"type": "string", "enum": hazards},
                            },
                            "observations": {
                                "type": "array",
                                "items": {"type": "string"},
                            },
                        },
                        "required": [
                            "caption",
                            "disaster_evidence",
                            "hazards",
                            "observations",
                        ],
                    },
                }
            },
        }
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        try:
            async with self._semaphore:
                async with httpx.AsyncClient(
                    timeout=self.timeout_seconds,
                    transport=self._transport,
                ) as client:
                    response = await client.post(
                        OPENAI_RESPONSES_URL,
                        headers=headers,
                        json=payload,
                    )
        except (httpx.TimeoutException, httpx.HTTPError) as exc:
            raise CaptionProviderError("OpenAI image screening is unavailable") from exc
        if response.status_code != 200:
            raise CaptionProviderError("OpenAI image screening is unavailable")
        try:
            envelope = response.json()
            content = _openai_output_text(envelope)
        except (ValueError, KeyError, IndexError, TypeError) as exc:
            raise CaptionProviderError("OpenAI image screening returned an invalid response") from exc
        result = _parse_model_content(content)
        return CaptionResult(
            caption=result["caption"],
            model=self.model[:180],
            provider="openai",
            evidence=result["disaster_evidence"],
            hazards=tuple(result["hazards"]),
            observations=tuple(result["observations"]),
            prompt_version=OPENAI_PROMPT_VERSION,
        )


def _openai_output_text(envelope: object) -> str:
    if not isinstance(envelope, dict) or not isinstance(envelope.get("output"), list):
        raise CaptionProviderError("OpenAI image screening returned an invalid response")
    for item in envelope["output"]:
        if not isinstance(item, dict) or item.get("type") != "message":
            continue
        for content in item.get("content", []):
            if isinstance(content, dict) and content.get("type") == "output_text":
                text = content.get("text")
                if isinstance(text, str):
                    return text
    raise CaptionProviderError("OpenAI image screening returned no assessment")


def _provider_name(model: str) -> str:
    provider = model.rsplit(":", 1)[1] if ":" in model else "auto"
    return f"huggingface:{provider}"[:80]


def _screening_prompt() -> str:
    hazards = ", ".join(sorted(CANONICAL_HAZARDS))
    return (
        "Analyze only what is visibly present in this image for disaster-report screening. "
        "Do not infer location, date, cause, authenticity, scale, or severity. If the visual "
        "evidence is weak or could be an ordinary scene, use unclear. Return JSON only, with "
        "exactly these keys: caption (one or two factual sentences), disaster_evidence "
        '(exactly "yes", "no", or "unclear"), hazards (an array using only these canonical '
        f"values: {hazards}), and observations (up to {MAX_OBSERVATIONS} short visible facts). "
        "Use an empty hazards array when no canonical hazard is visibly supported."
    )


def _strip_json_fence(content: str) -> str:
    stripped = content.strip()
    match = re.fullmatch(r"```(?:json)?\s*(.*?)\s*```", stripped, re.DOTALL | re.IGNORECASE)
    return match.group(1).strip() if match else stripped


def _parse_model_content(content: object) -> dict[str, object]:
    if not isinstance(content, str):
        raise CaptionProviderError("Hosted image screening returned an invalid response")
    try:
        payload = json.loads(_strip_json_fence(content))
    except (json.JSONDecodeError, TypeError) as exc:
        raise CaptionProviderError("Hosted image screening returned malformed JSON") from exc
    if not isinstance(payload, dict):
        raise CaptionProviderError("Hosted image screening returned an invalid response")
    if not {"caption", "disaster_evidence", "hazards", "observations"} <= payload.keys():
        raise CaptionProviderError("Hosted image screening omitted required evidence fields")

    caption = _normalized_text(payload["caption"])
    evidence = payload["disaster_evidence"]
    hazards = payload["hazards"]
    observations = payload["observations"]
    if not caption or len(caption) > MAX_CAPTION_CHARS:
        raise CaptionProviderError("Hosted image screening returned an invalid caption")
    if evidence not in {"yes", "no", "unclear"}:
        raise CaptionProviderError("Hosted image screening returned invalid evidence")
    if (
        not isinstance(hazards, list)
        or len(hazards) > MAX_HAZARDS
        or any(not isinstance(item, str) or item not in CANONICAL_HAZARDS for item in hazards)
        or len(hazards) != len(set(hazards))
    ):
        raise CaptionProviderError("Hosted image screening returned invalid hazards")
    if not isinstance(observations, list) or len(observations) > MAX_OBSERVATIONS:
        raise CaptionProviderError("Hosted image screening returned invalid observations")
    normalized_observations: list[str] = []
    for observation in observations:
        if not isinstance(observation, str):
            raise CaptionProviderError("Hosted image screening returned invalid observations")
        normalized = _normalized_text(observation)
        if not normalized or len(normalized) > MAX_OBSERVATION_CHARS:
            raise CaptionProviderError("Hosted image screening returned invalid observations")
        normalized_observations.append(normalized)
    return {
        "caption": caption,
        "disaster_evidence": evidence,
        "hazards": hazards,
        "observations": normalized_observations,
    }


def triage_caption(caption: str) -> TriageResult:
    """Run the deterministic half of image screening against visible-description text."""

    normalized = _normalized_text(caption)
    taxonomy_hazard = classify_hazard(normalized)
    if taxonomy_hazard != "other":
        return TriageResult(
            decision="accepted",
            reason=f"Visible description contains {taxonomy_hazard.replace('_', ' ')} evidence",
            inferred_hazard=taxonomy_hazard,
        )
    for hazard, pattern in VISIBLE_DISASTER_PATTERNS:
        if pattern.search(normalized):
            return TriageResult(
                decision="accepted",
                reason=f"Visible description contains {hazard.replace('_', ' ')} or damage evidence",
                inferred_hazard=hazard,
            )
    if any(pattern.search(normalized) for pattern in CLEAR_ORDINARY_PATTERNS):
        return TriageResult(
            decision="rejected",
            reason="Visible description clearly matches an ordinary scene without disaster evidence",
            inferred_hazard="other",
        )
    return TriageResult(
        decision="needs_volunteer_review",
        reason="Visible description is ambiguous and needs a volunteer to review the evidence",
        inferred_hazard="other",
    )


def triage_assessment(result: CaptionResult) -> TriageResult:
    combined = ". ".join((result.caption, *result.observations))
    deterministic = triage_caption(combined)
    model_hazards = set(result.hazards)
    if (
        result.evidence == "yes"
        and deterministic.decision == "accepted"
        and deterministic.inferred_hazard in model_hazards
    ):
        hazard = deterministic.inferred_hazard
        return TriageResult(
            decision="accepted",
            reason=(
                "AI visible-evidence assessment and the disaster keyword policy "
                f"agree on {hazard.replace('_', ' ')}"
            ),
            inferred_hazard=hazard,
        )
    if (
        result.evidence == "no"
        and not model_hazards
        and deterministic.decision == "rejected"
    ):
        return TriageResult(
            decision="rejected",
            reason="AI assessment and the ordinary-scene policy agree that no disaster is visible",
            inferred_hazard="other",
        )
    return TriageResult(
        decision="needs_volunteer_review",
        reason="AI and deterministic evidence checks were uncertain or did not agree; a volunteer must review the image",
        inferred_hazard="other",
    )


def triage_report_assessment(result: CaptionResult, reported_hazard: str) -> TriageResult:
    """Accept only three-way agreement; every disagreement remains human-reviewable."""

    combined = ". ".join((result.caption, *result.observations))
    deterministic = triage_caption(combined)
    normalized_reported_hazard = reported_hazard.strip().lower().replace("-", "_").replace(" ", "_")
    if (
        result.evidence == "yes"
        and deterministic.decision == "accepted"
        and deterministic.inferred_hazard in set(result.hazards)
        and deterministic.inferred_hazard == normalized_reported_hazard
    ):
        hazard = deterministic.inferred_hazard
        return TriageResult(
            decision="accepted",
            reason=(
                "OpenAI visible evidence, the disaster keyword policy, and the "
                f"reported incident type agree on {hazard.replace('_', ' ')}"
            ),
            inferred_hazard=hazard,
        )
    return TriageResult(
        decision="needs_volunteer_review",
        reason=(
            "OpenAI, the disaster keyword policy, and the reported incident type "
            "were uncertain or did not all agree; a volunteer must review the image"
        ),
        inferred_hazard="other",
    )


def triage_unavailable() -> TriageResult:
    return TriageResult(
        decision="needs_volunteer_review",
        reason="AI image screening was unavailable; a volunteer must review the evidence",
        inferred_hazard="other",
    )


def triage_storage_unavailable() -> TriageResult:
    return TriageResult(
        decision="needs_volunteer_review",
        reason=(
            "The disaster checks agreed, but protected cloud evidence storage was unavailable; "
            "a volunteer must review the preserved local image"
        ),
        inferred_hazard="other",
    )
