from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request, status

from ..config import settings
from .registry import ModelRegistry
from .scenarios import flood_scenario, wildfire_scenario
from .schemas import PredictionRequest
from .service import MLInferenceService, MLUnavailableError, MLValidationError


router = APIRouter(prefix="/api/v1/ml", tags=["research-ml"])
registry = ModelRegistry(settings.ml_model_root)
service = MLInferenceService(registry)


def _check_payload_size(request: Request) -> None:
    raw = request.headers.get("content-length")
    if not raw:
        return
    try:
        length = int(raw)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid Content-Length header") from exc
    if length > settings.ml_max_payload_bytes:
        raise HTTPException(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
            detail=f"Prediction payload exceeds the {settings.ml_max_payload_bytes}-byte limit",
        )


@router.get("/models")
def list_models() -> dict:
    return registry.catalog()


@router.get("/health")
def model_health() -> dict:
    return registry.health()


@router.get("/models/{model_id}/scenarios/{scenario_id}")
def get_scenario(model_id: str, scenario_id: str) -> dict:
    try:
        definition = registry.definition(model_id)
        if definition.kind == "wildfire":
            return wildfire_scenario(scenario_id)
        return flood_scenario(registry.root, scenario_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc).strip("'")) from exc
    except (OSError, ValueError) as exc:
        raise HTTPException(status_code=503, detail="Synthetic scenario data is unavailable") from exc


@router.post("/predict")
def predict(payload: PredictionRequest, request: Request) -> dict:
    _check_payload_size(request)
    try:
        return service.predict(payload)
    except MLValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except MLUnavailableError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
