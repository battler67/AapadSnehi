from __future__ import annotations

import asyncio
import io

from PIL import Image, ImageDraw

from app.config import settings
from app.services.image_triage import OpenAIVisionCaptionClient, prepare_inference_image


def _synthetic_image() -> bytes:
    image = Image.new("RGB", (320, 220), "white")
    draw = ImageDraw.Draw(image)
    draw.rectangle((45, 45, 275, 175), fill="#2878c8")
    draw.ellipse((125, 75, 195, 145), fill="#f59e0b")
    output = io.BytesIO()
    image.save(output, format="PNG")
    return output.getvalue()


async def main() -> None:
    client = OpenAIVisionCaptionClient(
        api_key=settings.openai_api_key,
        model=settings.openai_vision_model,
        timeout_seconds=settings.openai_timeout_seconds,
        max_calls_per_hour=1,
    )
    prepared = prepare_inference_image(_synthetic_image(), media_type="image/png")
    result = await client.caption(prepared)
    print(f"provider={result.provider}")
    print(f"model={result.model}")
    print(f"evidence={result.evidence}")
    print(f"hazards={','.join(result.hazards) or 'none'}")
    print(f"description={result.caption}")


if __name__ == "__main__":
    asyncio.run(main())
