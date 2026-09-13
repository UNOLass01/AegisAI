"""Train a versioned fraud-detection model on synthetic data.

Usage:
    python ml/training/train.py --version v1
    python ml/training/train.py --version v2 --n-train 5000

Each run reproducibly (fixed seeds) writes:
    ml/models/model_<version>.pkl
    ml/evaluation/reports/model_<version>.json   (via evaluate.py)
"""
import argparse
import sys
from pathlib import Path

import joblib
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import RandomForestClassifier
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

sys.path.insert(0, str(Path(__file__).resolve().parent))

from dataset import (  # noqa: E402
    FEATURE_COLUMNS,
    LABEL_COLUMN,
    DatasetConfig,
    dataset_version_for,
    generate_dataset,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
MODELS_DIR = REPO_ROOT / "ml" / "models"

VERSION_CONFIGS: dict[str, DatasetConfig] = {
    # v1: clean baseline, healthy performance.
    "v1": DatasetConfig(n_samples=5000, seed=100),
    # v2: legitimate amounts shifted +30% (spending drift baked into training).
    "v2": DatasetConfig(n_samples=5000, seed=100, legit_amount_shift=0.30),
    # v3: 30% of fraud labels flipped to legitimate (labeling-pipeline bug).
    "v3": DatasetConfig(n_samples=5000, seed=100, fraud_label_flip=0.30),
}

# Held-out test seeds per version. v2 is evaluated under the same drift it
# was trained on (production reality); v1/v3 on clean data.
TEST_SEEDS = {"v1": 200, "v2": 200, "v3": 200}


def build_pipeline() -> Pipeline:
    preprocessor = ColumnTransformer(
        [
            ("num", StandardScaler(), ["transaction_amount", "hour_of_day"]),
            ("cat", OneHotEncoder(handle_unknown="ignore"), ["merchant_category"]),
        ]
    )
    return Pipeline(
        [
            ("preprocessor", preprocessor),
            (
                "classifier",
                RandomForestClassifier(n_estimators=100, random_state=42, n_jobs=-1),
            ),
        ]
    )


def train_version(version: str, n_train: int | None = None) -> Path:
    if version not in VERSION_CONFIGS:
        raise ValueError(f"Unknown version {version!r}. Choose from {sorted(VERSION_CONFIGS)}")
    base = VERSION_CONFIGS[version]
    config = DatasetConfig(
        n_samples=n_train or base.n_samples,
        seed=base.seed,
        fraud_rate=base.fraud_rate,
        legit_amount_shift=base.legit_amount_shift,
        fraud_label_flip=base.fraud_label_flip,
    )
    df = generate_dataset(config)
    model = build_pipeline()
    model.fit(df[FEATURE_COLUMNS], df[LABEL_COLUMN])

    MODELS_DIR.mkdir(parents=True, exist_ok=True)
    model_path = MODELS_DIR / f"model_{version}.pkl"
    joblib.dump(model, model_path)
    print(f"[{version}] trained on {len(df)} rows "
          f"(dataset={dataset_version_for(config)}) -> {model_path}")
    return model_path


def main() -> None:
    parser = argparse.ArgumentParser(description="Train a versioned fraud model.")
    parser.add_argument("--version", required=True, choices=sorted(VERSION_CONFIGS))
    parser.add_argument("--n-train", type=int, default=None)
    parser.add_argument("--skip-eval", action="store_true",
                        help="Skip writing the metrics report.")
    args = parser.parse_args()

    train_version(args.version, n_train=args.n_train)

    if not args.skip_eval:
        eval_path = REPO_ROOT / "ml" / "evaluation" / "evaluate.py"
        sys.path.insert(0, str(eval_path.parent))
        from evaluate import evaluate_version  # noqa: E402

        report = evaluate_version(args.version)
        print(f"[{args.version}] accuracy={report['accuracy']:.3f} "
              f"precision={report['precision']:.3f} recall={report['recall']:.3f} "
              f"f1={report['f1']:.3f}")


if __name__ == "__main__":
    main()
