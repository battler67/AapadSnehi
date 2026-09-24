from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest

from app.config import settings
from app.ml.routes import registry, service


def _sample(name: str) -> dict:
    return json.loads((settings.ml_model_root / "artifacts" / "handoff" / name).read_text(encoding="utf-8"))


def _request(model_id: str, source_payload: dict, *, source: str = "manual") -> dict:
    return {
        "modelId": model_id,
        "source": source,
        "features": source_payload,
        "unitsConfirmed": True,
    }


def test_catalog_is_allowlisted_and_does_not_expose_local_paths(client):
    response = client.get("/api/v1/ml/models")
    assert response.status_code == 200
    payload = response.json()
    assert {item["id"] for item in payload["models"]} == {
        "flood-random-forest-v2",
        "flood-xgboost-event-v2",
        "wildfire-unet-v1",
    }
    assert payload["unavailableModels"][0]["id"] == "landslide"
    assert "AapadSnehi_models" not in response.text
    assert all(item["operationallyValidated"] is False for item in payload["models"])
    flood = payload["models"][0]
    assert len(flood["features"]) == 71
    assert next(item for item in flood["features"] if item["name"] == "prcp(mm/day)")["unit"] == "mm/day"


def test_packaged_hosted_bundle_supports_flood_models_without_torch():
    from app.ml.registry import ModelRegistry

    packaged_root = Path(__file__).resolve().parents[1] / "model_artifacts"
    packaged = ModelRegistry(packaged_root)
    catalog = packaged.catalog()

    states = {item["id"]: item["availability"] for item in catalog["models"]}
    assert states["flood-random-forest-v2"]["available"] is True
    assert states["flood-xgboost-event-v2"]["available"] is True
    assert states["wildfire-unet-v1"]["available"] is False
    assert len(catalog["models"][0]["features"]) == 71


def test_missing_packaged_metadata_is_reported_without_catalog_failure(tmp_path):
    from app.ml.registry import ModelRegistry

    catalog = ModelRegistry(tmp_path).catalog()
    flood = next(item for item in catalog["models"] if item["id"] == "flood-random-forest-v2")
    assert flood["availability"]["status"] == "metadata_missing"
    assert flood["features"] == []


def test_health_verifies_all_artifacts_and_cache_reuses_model(client):
    response = client.get("/api/v1/ml/health")
    assert response.status_code == 200
    assert all(item["available"] for item in response.json()["models"].values())
    first = registry.load("flood-random-forest-v2")
    second = registry.load("flood-random-forest-v2")
    assert first is second


def test_incompatible_sklearn_is_reported_before_deserialization(client, monkeypatch):
    from app.ml import registry as registry_module

    real_version = registry_module.metadata.version

    def incompatible_version(package: str) -> str:
        return "1.9.0" if package == "scikit-learn" else real_version(package)

    monkeypatch.setattr(registry_module.metadata, "version", incompatible_version)
    isolated_registry = registry_module.ModelRegistry(settings.ml_model_root)
    status = isolated_registry.verify("flood-xgboost-event-v2")
    assert status["available"] is False
    assert status["status"] == "runtime_incompatible"
    assert "requires 1.7.1" in status["detail"]


def test_unexpected_inference_compatibility_error_is_safe_503(client, monkeypatch):
    def incompatible_predict(*args, **kwargs):
        raise AttributeError("private serialized estimator detail")

    monkeypatch.setattr(service, "_predict_flood", incompatible_predict)
    scenario = client.get("/api/v1/ml/models/flood-xgboost-event-v2/scenarios/low").json()
    response = client.post(
        "/api/v1/ml/predict",
        json=_request("flood-xgboost-event-v2", scenario["features"], source="synthetic"),
    )
    assert response.status_code == 503
    assert response.json() == {
        "detail": "The selected trusted model could not run in this runtime"
    }
    assert "private serialized estimator detail" not in response.text


def test_random_forest_reference_prediction(client):
    sample = _sample("random_forest_input.json")
    response = client.post(
        "/api/v1/ml/predict",
        json={
            **_request("flood-random-forest-v2", {"row": sample["rows"][0]}),
            "predictionTime": sample["prediction_time"],
            "latestInputAvailableAt": sample["latest_input_available_at"],
            "latestObservationTime": sample["latest_observation_time"],
        },
    )
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["outputDetails"]["dischargeM3S"] == pytest.approx(41.75717115160998)
    assert payload["confidence"] is None
    assert payload["riskLevel"] == "not_assessed"
    assert payload["operationallyValidated"] is False


def test_xgboost_reference_prediction_and_probabilities(client):
    sample = _sample("xgboost_input.json")
    response = client.post(
        "/api/v1/ml/predict",
        json=_request("flood-xgboost-event-v2", {"row": sample["rows"][0]}),
    )
    assert response.status_code == 200, response.text
    payload = response.json()
    score = payload["outputDetails"]["highFlowScore"]
    assert score == pytest.approx(0.00005828218411220035)
    assert sum(payload["classProbabilities"].values()) == pytest.approx(1.0)
    assert payload["outputDetails"]["reviewFlag"] is False
    assert "not_safe" in payload["riskLevel"]


def test_unet_reference_prediction_preserves_preprocessing(client):
    sample = _sample("unet_input.json")
    expected = _sample("unet_output.json")
    response = client.post(
        "/api/v1/ml/predict",
        json=_request("wildfire-unet-v1", {"channels": sample["channels"]}),
    )
    assert response.status_code == 200, response.text
    payload = response.json()
    actual = np.asarray(payload["outputDetails"]["scoreMap"])
    reference = np.asarray(expected["uncalibrated_probability_map"])
    assert actual.shape == (64, 64)
    assert np.allclose(actual, reference, rtol=1e-5, atol=1e-6)
    assert payload["outputDetails"]["validationAlertCutoff"] == pytest.approx(0.4495303297042897)
    assert payload["confidence"] is None


@pytest.mark.parametrize("model_id", ["flood-random-forest-v2", "flood-xgboost-event-v2", "wildfire-unet-v1"])
def test_each_model_accepts_its_low_synthetic_scenario(client, model_id):
    scenario = client.get(f"/api/v1/ml/models/{model_id}/scenarios/low")
    assert scenario.status_code == 200
    response = client.post(
        "/api/v1/ml/predict",
        json=_request(model_id, scenario.json()["features"], source="synthetic"),
    )
    assert response.status_code == 200, response.text
    assert response.json()["synthetic"] is True


def test_missing_feature_unseen_catchment_and_units_are_rejected(client):
    sample = _sample("random_forest_input.json")
    row = dict(sample["rows"][0])
    row.pop("discharge")
    response = client.post("/api/v1/ml/predict", json=_request("flood-random-forest-v2", {"row": row}))
    assert response.status_code == 422
    assert "Missing required features" in response.json()["detail"]

    row = dict(sample["rows"][0], catchment_id="99999")
    response = client.post("/api/v1/ml/predict", json=_request("flood-random-forest-v2", {"row": row}))
    assert response.status_code == 422
    assert "Unseen catchment" in response.json()["detail"]

    payload = _request("flood-random-forest-v2", {"row": sample["rows"][0]})
    payload["unitsConfirmed"] = False
    assert client.post("/api/v1/ml/predict", json=payload).status_code == 422


def test_wildfire_shape_existing_fire_and_future_sources_are_rejected(client):
    scenario = client.get("/api/v1/ml/models/wildfire-unet-v1/scenarios/low").json()
    channels = scenario["features"]["channels"]
    bad_shape = {**channels, "pr": [[0.0]]}
    response = client.post("/api/v1/ml/predict", json=_request("wildfire-unet-v1", {"channels": bad_shape}))
    assert response.status_code == 422
    assert "64×64" in response.json()["detail"]

    no_fire = {**channels, "PrevFireMask": [[0.0] * 64 for _ in range(64)]}
    response = client.post("/api/v1/ml/predict", json=_request("wildfire-unet-v1", {"channels": no_fire}))
    assert response.status_code == 422
    assert "ignition prediction" in response.json()["detail"]

    flood = client.get("/api/v1/ml/models/flood-random-forest-v2/scenarios/low").json()
    payload = _request("flood-random-forest-v2", flood["features"])
    payload["source"] = "weather_api"
    response = client.post("/api/v1/ml/predict", json=payload)
    assert response.status_code == 422
    assert "not connected" in response.json()["detail"]


def test_unknown_model_and_oversized_request_are_safe(client):
    response = client.post(
        "/api/v1/ml/predict",
        json=_request("../../untrusted-model", {"row": {}}),
    )
    assert response.status_code == 422
    assert "path" not in response.text.lower()

    response = client.post(
        "/api/v1/ml/predict",
        headers={"content-length": str(settings.ml_max_payload_bytes + 1)},
        json=_request("flood-random-forest-v2", {"row": {}}),
    )
    assert response.status_code == 413


def test_out_of_documented_range_returns_warning_not_silent_acceptance(client):
    scenario = client.get("/api/v1/ml/models/flood-random-forest-v2/scenarios/low").json()
    scenario["features"]["row"]["tavg(C)"] = 45.0
    response = client.post(
        "/api/v1/ml/predict",
        json=_request("flood-random-forest-v2", scenario["features"], source="synthetic"),
    )
    assert response.status_code == 200
    assert any("Average temperature" in warning for warning in response.json()["validationWarnings"])
