"""Model artifact store: loads versioned sklearn models + their metrics reports.

Paths resolve relative to the repo root so this works both locally
(`backend/app/services/...` -> repo `ml/...`) and in Docker (`/code/ml/...`),
and can be overridden with ML_MODELS_DIR / ML_REPORTS_DIR.
"""
import json
import os
from functools import lru_cache
from pathlib import Path

import joblib

REPO_ROOT = Path(__file__).resolve().parents[3]


def _default_dir(*parts: str) -> Path:
    """Locate <repo>/ml/... by walking up to the first ancestor containing ml/.

    Works locally (backend/app/services/... -> repo root) and in Docker
    (/code/app/services/... -> /code, where ml/ is copied next to app/).
    """
    for ancestor in Path(__file__).resolve().parents:
        if (ancestor / "ml").is_dir():
            return ancestor.joinpath(*parts)
    return REPO_ROOT.joinpath(*parts)


MODELS_DIR = Path(os.getenv("ML_MODELS_DIR", _default_dir("ml", "models")))
REPORTS_DIR = Path(os.getenv("ML_REPORTS_DIR", _default_dir("ml", "evaluation", "reports")))

FEATURE_COLUMNS = ["transaction_amount", "merchant_category", "hour_of_day"]


class UnknownModelVersionError(KeyError):
    pass


def available_versions() -> list[str]:
    versions: set[str] = set()
    if MODELS_DIR.exists():
        versions.update(p.stem.replace("model_", "") for p in MODELS_DIR.glob("model_*.pkl"))
    if REPORTS_DIR.exists():
        versions.update(p.stem.replace("model_", "") for p in REPORTS_DIR.glob("model_*.json"))
    return sorted(versions)


@lru_cache(maxsize=16)
def load_model(version: str):
    path = MODELS_DIR / f"model_{version}.pkl"
    if not path.exists():
        raise UnknownModelVersionError(
            f"Model version {version!r} not found. Available: {available_versions()}"
        )
    return joblib.load(path)


def get_metrics(version: str) -> dict | None:
    path = REPORTS_DIR / f"model_{version}.json"
    if not path.exists():
        return None
    return json.loads(path.read_text())


def artifact_present(version: str) -> bool:
    return (MODELS_DIR / f"model_{version}.pkl").exists()


def predict_one(record: dict, version: str) -> dict:
    import pandas as pd

    model = load_model(version)
    frame = pd.DataFrame([record], columns=FEATURE_COLUMNS)
    proba = float(model.predict_proba(frame)[0, 1])
    return {
        "model_version": version,
        "is_fraud": proba >= 0.5,
        "fraud_probability": round(proba, 4),
    }
