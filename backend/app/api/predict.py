"""Model serving routes: POST /predict and GET /models."""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.services.model_store import (
    UnknownModelVersionError,
    artifact_present,
    available_versions,
    get_metrics,
    predict_one,
)

router = APIRouter(tags=["models"])


class PredictRequest(BaseModel):
    transaction_amount: float = Field(gt=0, le=1_000_000)
    merchant_category: str = Field(min_length=1, max_length=50)
    hour_of_day: int = Field(ge=0, le=23)
    model_version: str = "v1"


class PredictResponse(BaseModel):
    model_version: str
    is_fraud: bool
    fraud_probability: float


@router.post("/predict", response_model=PredictResponse)
def predict(body: PredictRequest) -> dict:
    try:
        return predict_one(
            {
                "transaction_amount": body.transaction_amount,
                "merchant_category": body.merchant_category,
                "hour_of_day": body.hour_of_day,
            },
            version=body.model_version,
        )
    except UnknownModelVersionError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


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
