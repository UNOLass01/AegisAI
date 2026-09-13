"""Evaluate a trained model version on its held-out set and write a JSON report.

Usage:
    python ml/evaluation/evaluate.py --version v1

Writes:
    ml/evaluation/reports/model_<version>.json
"""
import argparse
import datetime
import json
import sys
from pathlib import Path

import joblib
import pandas as pd
from sklearn.metrics import (
    accuracy_score,
    confusion_matrix,
    f1_score,
    precision_score,
    recall_score,
)

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "training"))

from dataset import (  # noqa: E402
    FEATURE_COLUMNS,
    LABEL_COLUMN,
    DatasetConfig,
    dataset_version_for,
    generate_dataset,
)
from train import TEST_SEEDS, VERSION_CONFIGS  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[2]
MODELS_DIR = REPO_ROOT / "ml" / "models"
REPORTS_DIR = REPO_ROOT / "ml" / "evaluation" / "reports"

N_TEST = 2000


def evaluate_version(version: str, n_test: int = N_TEST) -> dict:
    if version not in VERSION_CONFIGS:
        raise ValueError(f"Unknown version {version!r}. Choose from {sorted(VERSION_CONFIGS)}")
    model_path = MODELS_DIR / f"model_{version}.pkl"
    if not model_path.exists():
        raise FileNotFoundError(f"Model artifact missing: {model_path}. Train it first.")
    model = joblib.load(model_path)

    train_config = VERSION_CONFIGS[version]
    test_config = DatasetConfig(
        n_samples=n_test,
        seed=TEST_SEEDS[version],
        # v2 is evaluated under the same +30% drift it faces in production.
        legit_amount_shift=train_config.legit_amount_shift,
    )
    test_df = generate_dataset(test_config)
    y_true = test_df[LABEL_COLUMN]
    y_pred = pd.Series(model.predict(test_df[FEATURE_COLUMNS]), index=test_df.index)
    tn, fp, fn, tp = confusion_matrix(y_true, y_pred).ravel()

    report = {
        "model_version": version,
        "accuracy": round(float(accuracy_score(y_true, y_pred)), 4),
        "precision": round(float(precision_score(y_true, y_pred, zero_division=0)), 4),
        "recall": round(float(recall_score(y_true, y_pred, zero_division=0)), 4),
        "f1": round(float(f1_score(y_true, y_pred, zero_division=0)), 4),
        "true_positives": int(tp),
        "false_positives": int(fp),
        "true_negatives": int(tn),
        "false_negatives": int(fn),
        "n_test": int(n_test),
        "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "dataset_version": dataset_version_for(test_config),
    }
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    report_path = REPORTS_DIR / f"model_{version}.json"
    report_path.write_text(json.dumps(report, indent=2))
    print(f"[{version}] report -> {report_path}")
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate a trained model version.")
    parser.add_argument("--version", required=True, choices=sorted(VERSION_CONFIGS))
    parser.add_argument("--n-test", type=int, default=N_TEST)
    args = parser.parse_args()
    report = evaluate_version(args.version, n_test=args.n_test)
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
