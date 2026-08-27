"""Make one hosted vision request using a fixed public documentation image.

This verification helper deliberately accepts no local image path, so it cannot be
used accidentally to upload citizen evidence. The provider call may consume Hugging
Face Inference Providers credit.
"""

from __future__ import annotations

import asyncio
import json
import subprocess

import httpx

from app.services.image_triage import (
    HuggingFaceVisionCaptionClient,
    prepare_inference_image,
    triage_assessment,
)


PUBLIC_IMAGE_URL = (
    "https://huggingface.co/datasets/huggingface/documentation-images/"
    "resolve/main/transformers/tasks/car.jpg"
)


def _cli_token() -> str:
    result = subprocess.run(
        ["hf", "auth", "token", "--quiet"],
        check=True,
        capture_output=True,
        text=True,
    )
    token = result.stdout.strip()
    if not token:
        raise RuntimeError("Hugging Face CLI has no active token")
    return token


async def main() -> None:
    token = _cli_token()
    async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
        response = await client.get(PUBLIC_IMAGE_URL)
        response.raise_for_status()
    prepared = prepare_inference_image(response.content, media_type="image/jpeg")
    provider = HuggingFaceVisionCaptionClient(
        hf_token=token,
        max_calls_per_hour=1,
    )
    assessment = await provider.caption(prepared)
    triage = triage_assessment(assessment)
    print(
        json.dumps(
            {
                "publicImage": PUBLIC_IMAGE_URL,
                "model": assessment.model,
                "provider": assessment.provider,
                "promptVersion": assessment.prompt_version,
                "caption": assessment.caption,
                "disasterEvidence": assessment.evidence,
                "hazards": list(assessment.hazards),
                "observations": list(assessment.observations),
                "triage": triage.decision,
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    asyncio.run(main())
