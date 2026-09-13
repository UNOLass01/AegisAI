"""Model serving routes: POST /predict and GET /models."""
import time

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from app.services.logger import get_logger, log_prediction
from app.services.metrics import (
    PREDICT_CORRECT,
    PREDICT_FLAGGED,
    PREDICT_LATENCY,
    PREDICT_REQUESTS,
    PREDICT_TRUE_POSITIVES,
)
from app.services.model_store import (
    UnknownModelVersionError,
    artifact_present,
    available_versions,
    get_metrics,
    predict_one,
)

router = APIRouter(tags=["models"])
logger = get_logger("aegis")


class PredictRequest(BaseModel):
    transaction_amount: float = Field(gt=0, le=1_000_000)
    merchant_category: str = Field(min_length=1, max_length=50)
    hour_of_day: int = Field(ge=0, le=23)
    model_version: str = "v1"
    # Optional ground truth supplied by the traffic-simulation harness so the
    # precision-proxy panel (correct / total) can be computed. Ignored otherwise.
    ground_truth: bool | None = None


class PredictResponse(BaseModel):
    model_version: str
    is_fraud: bool
    fraud_probability: float


@router.post("/predict", response_model=PredictResponse)
def predict(body: PredictRequest, request: Request) -> dict:
    request.state.model_version = body.model_version
    start = time.perf_counter()
    try:
        result = predict_one(
            {
                "transaction_amount": body.transaction_amount,
                "merchant_category": body.merchant_category,
                "hour_of_day": body.hour_of_day,
            },
            version=body.model_version,
        )
    except UnknownModelVersionError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    latency_ms = (time.perf_counter() - start) * 1000.0
    PREDICT_REQUESTS.labels(model_version=body.model_version).inc()
    PREDICT_LATENCY.labels(model_version=body.model_version).observe(latency_ms / 1000.0)
    if body.ground_truth is not None and body.ground_truth == result["is_fraud"]:
        PREDICT_CORRECT.labels(model_version=body.model_version).inc()
    if result["is_fraud"]:
        PREDICT_FLAGGED.labels(model_version=body.model_version).inc()
        if body.ground_truth is True:
            PREDICT_TRUE_POSITIVES.labels(model_version=body.model_version).inc()
    log_prediction(
        logger,
        model_version=body.model_version,
        fraud_probability=result["fraud_probability"],
        is_fraud=result["is_fraud"],
        latency_ms=latency_ms,
    )
    return result


@router.get("/models")
def list_models() -> dict:
    versions = available_versions()
    return {
        "models": [
            {
                "model_version": version,
                "metrics": get_metrics(version),
                "artifact_present": artifact_present(version),
            }
            for version in versions
        ]
    }
