"""Synthetic fraud/anomaly-detection tabular dataset.

One consistent generator is used for every model version. Versions differ only
through explicit, recorded perturbations:

- v1: clean data (healthy baseline).
- v2: legitimate `transaction_amount` shifted +30% (spending drift baked into
  the training data; evaluated under the same drift -> false-positive rise).
- v3: 30% of fraud labels flipped to legitimate (labeling-pipeline bug ->
  recall degradation).

All randomness flows from explicit seeds, so every artifact is reproducible.
"""
from dataclasses import dataclass

import numpy as np
import pandas as pd

MERCHANT_CATEGORIES = ["grocery", "fuel", "travel", "electronics", "restaurants"]
CATEGORY_PROBS = [0.32, 0.22, 0.12, 0.14, 0.20]
# Fraud concentrates mildly in electronics/travel...
FRAUD_CATEGORY_PROBS = [0.20, 0.12, 0.20, 0.25, 0.23]
# ... and in night hours (0-5 carry 40% of fraud mass vs 25% uniform).
HOUR_PROBS = np.array([0.40 / 6] * 6 + [0.60 / 18] * 18)

FEATURE_COLUMNS = ["transaction_amount", "merchant_category", "hour_of_day"]
LABEL_COLUMN = "is_fraud"

# Canonical dataset identifiers recorded in every metrics report.
DATASET_CLEAN = "synthetic-clean-v1"
DATASET_DRIFTED = "synthetic-drifted-amount-plus30pct-v1"


@dataclass(frozen=True)
class DatasetConfig:
    n_samples: int = 5000
    seed: int = 42
    fraud_rate: float = 0.08
    # +0.30 means legitimate transaction_amount *= 1.30 (v2 drift).
    legit_amount_shift: float = 0.0
    # Fraction of fraud rows whose label is flipped to 0 (v3 labeling bug).
    fraud_label_flip: float = 0.0


def generate_dataset(config: DatasetConfig) -> pd.DataFrame:
    rng = np.random.default_rng(config.seed)
    n = config.n_samples

    is_fraud = rng.random(n) < config.fraud_rate

    # Fraudulent transactions skew larger, happen at night, and concentrate
    # in electronics/travel. Legitimate traffic is smaller, daytime, everyday
    # categories. This gives a healthy model strong, learnable signal.
    amount = np.where(
        is_fraud,
        rng.lognormal(mean=4.9, sigma=0.6, size=n),
        rng.lognormal(mean=3.2, sigma=0.7, size=n),
    ).astype(float)
    amount = np.clip(amount, 1.0, 5000.0)

    if config.legit_amount_shift:
        amount[~is_fraud] = np.clip(
            amount[~is_fraud] * (1.0 + config.legit_amount_shift), 1.0, 5000.0
        )

    merchant_category = np.where(
        is_fraud,
        rng.choice(MERCHANT_CATEGORIES, size=n, p=FRAUD_CATEGORY_PROBS),
        rng.choice(MERCHANT_CATEGORIES, size=n, p=CATEGORY_PROBS),
    )
    hour_of_day = np.where(
        is_fraud,
        rng.choice(24, size=n, p=HOUR_PROBS),
        rng.integers(0, 24, size=n),
    )

    labels = is_fraud.astype(int)
    if config.fraud_label_flip:
        fraud_idx = np.flatnonzero(labels == 1)
        n_flip = int(len(fraud_idx) * config.fraud_label_flip)
        if n_flip:
            flip_idx = rng.choice(fraud_idx, size=n_flip, replace=False)
            labels[flip_idx] = 0

    return pd.DataFrame(
        {
            "transaction_amount": np.round(amount, 2),
            "merchant_category": merchant_category,
            "hour_of_day": hour_of_day,
            LABEL_COLUMN: labels,
        }
    )


def dataset_version_for(config: DatasetConfig) -> str:
    if config.legit_amount_shift:
        return DATASET_DRIFTED
    return DATASET_CLEAN
