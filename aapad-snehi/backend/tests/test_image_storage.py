from __future__ import annotations

import asyncio

import pytest

from app.services import image_storage
from app.services.image_storage import (
    CloudinaryImageStore,
    ImageStorageError,
    parse_cloudinary_credentials,
)


def test_cloudinary_credentials_require_a_complete_connection_value_or_three_parts():
    parsed = parse_cloudinary_credentials(
        "cloudinary://12345:secret%2Fvalue@sample-cloud"
    )
    assert parsed is not None
    assert parsed.cloud_name == "sample-cloud"
    assert parsed.api_key == "12345"
    assert parsed.api_secret == "secret/value"

    assert parse_cloudinary_credentials("only-one-key") is None
    assert parse_cloudinary_credentials("", cloud_name="cloud", api_key="key") is None
    assert parse_cloudinary_credentials(
        "",
        cloud_name="cloud",
        api_key="key",
        api_secret="secret",
    ) is not None


def test_cloudinary_store_uploads_authenticated_assets_and_deletes_them(monkeypatch):
    calls: dict[str, object] = {}

    monkeypatch.setattr(image_storage.cloudinary, "config", lambda **kwargs: calls.setdefault("config", kwargs))

    def upload(file, **kwargs):
        calls["uploaded"] = file.read()
        calls["upload_options"] = kwargs
        return {
            "public_id": kwargs["public_id"],
            "asset_id": "asset-123",
            "format": "jpg",
        }

    def destroy(public_id, **kwargs):
        calls["destroy"] = (public_id, kwargs)
        return {"result": "ok"}

    monkeypatch.setattr(image_storage.cloudinary.uploader, "upload", upload)
    monkeypatch.setattr(image_storage.cloudinary.uploader, "destroy", destroy)
    store = CloudinaryImageStore(
        connection_value="cloudinary://key:secret@example-cloud"
    )

    stored = asyncio.run(store.upload(b"original-image", tracking_id="AS-20260821-ABC12345"))
    asyncio.run(store.delete(stored.public_id))

    assert stored.asset_id == "asset-123"
    assert calls["uploaded"] == b"original-image"
    assert calls["upload_options"]["type"] == "authenticated"
    assert calls["upload_options"]["overwrite"] is False
    assert calls["destroy"][1]["type"] == "authenticated"
    assert calls["destroy"][1]["invalidate"] is True


def test_cloudinary_store_creates_short_lived_authenticated_review_url(monkeypatch):
    calls: dict[str, object] = {}
    monkeypatch.setattr(image_storage.cloudinary, "config", lambda **_: None)

    def signed_url(public_id, image_format, **kwargs):
        calls.update({"public_id": public_id, "format": image_format, **kwargs})
        return "https://api.cloudinary.com/private-review"

    monkeypatch.setattr(image_storage.cloudinary.utils, "private_download_url", signed_url)
    store = CloudinaryImageStore(
        connection_value="cloudinary://key:secret@example-cloud",
        review_url_seconds=300,
        clock=lambda: 1_000,
    )

    url = asyncio.run(store.temporary_url("aapad-snehi/reports/test", "jpg"))

    assert url.startswith("https://")
    assert calls["type"] == "authenticated"
    assert calls["expires_at"] == 1_300


def test_unconfigured_store_never_attempts_network():
    store = CloudinaryImageStore(connection_value="only-one-key")
    assert store.configured is False
    with pytest.raises(ImageStorageError, match="not configured"):
        asyncio.run(store.upload(b"image", tracking_id="AS-20260821-ABC12345"))
