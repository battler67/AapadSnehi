from __future__ import annotations

import asyncio
import io
from datetime import datetime, timezone

from PIL import Image

from app.config import settings
from app.services.image_storage import CloudinaryImageStore


def _synthetic_image() -> bytes:
    output = io.BytesIO()
    Image.new("RGB", (32, 32), "#2878c8").save(output, format="PNG")
    return output.getvalue()


async def main() -> None:
    store = CloudinaryImageStore(
        connection_value=settings.cloudinary_key,
        cloud_name=settings.cloudinary_cloud_name,
        api_key=settings.cloudinary_api_key,
        api_secret=settings.cloudinary_api_secret,
        review_url_seconds=settings.cloudinary_review_url_seconds,
    )
    if not store.configured:
        raise SystemExit(
            "Cloudinary is not fully configured; provide a cloudinary:// URL or all three credential parts"
        )
    tracking_id = f"AS-{datetime.now(timezone.utc):%Y%m%d}-SMOKE001"
    stored = await store.upload(_synthetic_image(), tracking_id=tracking_id)
    try:
        review_url = await store.temporary_url(stored.public_id, stored.format)
        print(f"upload=ok signed_review_url={review_url.startswith('https://')}")
    finally:
        await store.delete(stored.public_id)
        print("cleanup=ok")


if __name__ == "__main__":
    asyncio.run(main())
