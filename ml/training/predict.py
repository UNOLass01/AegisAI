"""Load a versioned model and serve predictions (CLI + importable helpers).

Usage:
    python ml/training/predict.py --version v1 --amount 250 --category electronics --hour 3
"""
import argparse
import json
import sys
from pathlib import Path

import joblib
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))

from dataset import FEATURE_COLUMNS, MERCHANT_CATEGORIES  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[2]
MODELS_DIR = REPO_ROOT / "ml" / "models"

_model_cache: dict[str, object] = {}


def available_versions() -> list[str]:
    if not MODELS_DIR.exists():
        return []
    return sorted(
        p.stem.replace("model_", "")
        for p in MODELS_DIR.glob("model_*.pkl")
    )


def load_model(version: str):
    if version not in _model_cache:
        model_path = MODELS_DIR / f"model_{version}.pkl"
        if not model_path.exists():
            raise FileNotFoundError(
                f"Model {version!r} not found at {model_path}. "
                f"Available: {available_versions()}"
            )
        _model_cache[version] = joblib.load(model_path)
    return _model_cache[version]


def predict_records(records: list[dict], version: str) -> list[dict]:
    model = load_model(version)
    frame = pd.DataFrame(records, columns=FEATURE_COLUMNS)
    probas = model.predict_proba(frame)[:, 1]
    labels = (probas >= 0.5).astype(int)
    return [
        {
            "is_fraud": bool(label),
            "fraud_probability": round(float(proba), 4),
            "model_version": version,
        }
        for label, proba in zip(labels, probas)
    ]


def main() -> None:
    parser = argparse.ArgumentParser(description="Predict fraud for one transaction.")
    parser.add_argument("--version", default="v1")
    parser.add_argument("--amount", type=float, required=True)
    parser.add_argument("--category", choices=MERCHANT_CATEGORIES, required=True)
    parser.add_argument("--hour", type=int, required=True)
    args = parser.parse_args()
    result = predict_records(
        [
            {
                "transaction_amount": args.amount,
                "merchant_category": args.category,
                "hour_of_day": args.hour,
            }
        ],
        version=args.version,
    )[0]
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
