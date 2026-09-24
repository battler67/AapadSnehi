from unittest.mock import AsyncMock

from app import main
from app.services.image_triage import CaptionResult, CaptionProviderError
from test_flood import create


def test_optional_screening_is_private_advisory_and_retry_safe(client, monkeypatch, valid_jpeg_bytes):
    caption = AsyncMock(return_value=CaptionResult(
        caption="Water visible on a road", model="test-model", provider="openai",
        evidence="yes", hazards=("flood",), observations=("Standing water",)))
    monkeypatch.setattr(main.caption_client, "caption", caption)
    receipt, payload = create(client)
    assert caption.await_count == 0  # Text-only report never calls AI.
    headers = {"X-Reporter-Token": payload["reporter_token"]}
    url = f"/api/flood/reports/{receipt['reportId']}/media"
    files = {"image": ("test.jpg", valid_jpeg_bytes, "image/jpeg")}
    assert client.post(url, files=files).status_code == 403
    assert client.post(url, files={"image": ("fake.jpg", b"bad", "image/jpeg")}, headers=headers).status_code == 422
    assert caption.await_count == 0
    response = client.post(url, files=files, headers=headers)
    assert response.status_code == 201, response.text
    assert response.json()["review"]["status"] == "screened"
    assert caption.await_count == 1
    assert client.post(url, files=files, headers=headers).json() == response.json()
    assert caption.await_count == 1
    own = client.get(f"/api/flood/reports/{receipt['reportId']}", headers=headers).json()
    assert own["reviewStatus"] == "unverified"
    assert own["media"][0]["review"]["caption"] == "Water visible on a road"
    public = client.get(f"/api/flood/incidents/{receipt['incidentId']}")
    assert "Water visible" not in public.text
    assert public.json()["verification"] == "unverified"
    assert client.get(f"/api/flood/media/{response.json()['id']}").status_code == 403


def test_provider_failure_keeps_photo_and_report(client, monkeypatch, valid_jpeg_bytes):
    caption = AsyncMock(side_effect=CaptionProviderError("secret provider detail"))
    monkeypatch.setattr(main.caption_client, "caption", caption)
    receipt, payload = create(client)
    response = client.post(f"/api/flood/reports/{receipt['reportId']}/media",
        files={"image": ("test.jpg", valid_jpeg_bytes, "image/jpeg")},
        headers={"X-Reporter-Token": payload["reporter_token"]})
    assert response.status_code == 201
    assert response.json()["attached"]
    assert response.json()["review"]["status"] == "unavailable"
    assert "secret provider detail" not in response.text
    assert client.get(f"/api/flood/reports/{receipt['reportId']}",
        headers={"X-Reporter-Token": payload["reporter_token"]}).json()["mediaCount"] == 1
