from __future__ import annotations

import asyncio
import io
import re
import time
from dataclasses import dataclass
from typing import Callable
from urllib.parse import unquote, urlparse

import cloudinary
import cloudinary.uploader
import cloudinary.utils


class ImageStorageError(RuntimeError):
    """A secret-safe Cloudinary failure."""


@dataclass(frozen=True)
class CloudinaryCredentials:
    cloud_name: str
    api_key: str
    api_secret: str


@dataclass(frozen=True)
class StoredImage:
    public_id: str
    asset_id: str
    format: str


def parse_cloudinary_credentials(
    connection_value: str,
    *,
    cloud_name: str = "",
    api_key: str = "",
    api_secret: str = "",
) -> CloudinaryCredentials | None:
    """Accept a CLOUDINARY_URL-shaped value or three explicit credential parts."""

    if connection_value:
        parsed = urlparse(connection_value)
        if (
            parsed.scheme == "cloudinary"
            and parsed.username
            and parsed.password
            and parsed.hostname
            and parsed.path in {"", "/"}
        ):
            return CloudinaryCredentials(
                cloud_name=parsed.hostname,
                api_key=unquote(parsed.username),
                api_secret=unquote(parsed.password),
            )
        return None
    if cloud_name and api_key and api_secret:
        return CloudinaryCredentials(
            cloud_name=cloud_name,
            api_key=api_key,
            api_secret=api_secret,
        )
    return None


class CloudinaryImageStore:
    def __init__(
        self,
        *,
        connection_value: str = "",
        cloud_name: str = "",
        api_key: str = "",
        api_secret: str = "",
        review_url_seconds: int = 300,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self.credentials = parse_cloudinary_credentials(
            connection_value,
            cloud_name=cloud_name,
            api_key=api_key,
            api_secret=api_secret,
        )
        self.review_url_seconds = max(60, min(3600, review_url_seconds))
        self._clock = clock

    @property
    def configured(self) -> bool:
        return self.credentials is not None

    def _configure(self) -> None:
        if self.credentials is None:
            raise ImageStorageError("Cloudinary image storage is not configured")
        cloudinary.config(
            cloud_name=self.credentials.cloud_name,
            api_key=self.credentials.api_key,
            api_secret=self.credentials.api_secret,
            secure=True,
        )

    async def upload(self, content: bytes, *, tracking_id: str) -> StoredImage:
        if not re.fullmatch(r"AS-[A-Z0-9-]{8,40}", tracking_id):
            raise ImageStorageError("Image storage received an invalid tracking identifier")

        def perform_upload() -> StoredImage:
            self._configure()
            try:
                result = cloudinary.uploader.upload(
                    io.BytesIO(content),
                    public_id=f"aapad-snehi/reports/{tracking_id.lower()}",
                    resource_type="image",
                    type="authenticated",
                    overwrite=False,
                    unique_filename=False,
                    use_filename=False,
                )
            except Exception as exc:
                raise ImageStorageError("Cloudinary image upload is unavailable") from exc
            public_id = result.get("public_id") if isinstance(result, dict) else None
            asset_id = result.get("asset_id") if isinstance(result, dict) else None
            image_format = result.get("format") if isinstance(result, dict) else None
            if not all(isinstance(value, str) and value for value in (public_id, asset_id, image_format)):
                raise ImageStorageError("Cloudinary image upload returned an invalid response")
            return StoredImage(
                public_id=public_id[:255],
                asset_id=asset_id[:255],
                format=image_format[:20],
            )

        return await asyncio.to_thread(perform_upload)

    async def delete(self, public_id: str) -> None:
        if not public_id:
            return

        def perform_delete() -> None:
            self._configure()
            try:
                result = cloudinary.uploader.destroy(
                    public_id,
                    resource_type="image",
                    type="authenticated",
                    invalidate=True,
                )
            except Exception as exc:
                raise ImageStorageError("Cloudinary image deletion is unavailable") from exc
            outcome = result.get("result") if isinstance(result, dict) else None
            if outcome not in {"ok", "not found"}:
                raise ImageStorageError("Cloudinary did not confirm image deletion")

        await asyncio.to_thread(perform_delete)

    async def temporary_url(self, public_id: str, image_format: str) -> str:
        if not public_id or not image_format:
            raise ImageStorageError("Stored image metadata is incomplete")

        def create_url() -> str:
            self._configure()
            try:
                url = cloudinary.utils.private_download_url(
                    public_id,
                    image_format,
                    resource_type="image",
                    type="authenticated",
                    expires_at=int(self._clock()) + self.review_url_seconds,
                )
            except Exception as exc:
                raise ImageStorageError("Cloudinary review access is unavailable") from exc
            if not isinstance(url, str) or not url.startswith("https://"):
                raise ImageStorageError("Cloudinary returned an invalid review URL")
            return url

        return await asyncio.to_thread(create_url)
