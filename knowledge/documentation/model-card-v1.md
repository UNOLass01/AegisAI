# Model Card — Fraud Detection v1 (baseline)

- **Version:** v1
- **Status:** healthy baseline, previously in production
- **Model:** RandomForestClassifier (100 trees), amount/hour standardized, merchant_category one-hot
- **Training data:** `synthetic-clean-v1` — 5000 rows, seed 100, 8% fraud rate
- **Eval data:** `synthetic-clean-v1` — 2000 rows, seed 200

## Metrics (held-out)

| accuracy | precision | recall | F1 |
|---|---|---|---|
| 0.9525 | 0.7400 | 0.6647 | 0.7000 |

Confusion: TP=117, FP=42, TN=1791, FN=50 (n=2000).

## Intended use

Real-time scoring of card transactions via `POST /predict`. Flags roughly the
top-risk transactions for manual review.

## Limitations

- Recall 0.66 means about one third of fraud is missed; tune the 0.5 threshold
  if recall matters more than precision for a given deployment.
- Trained on synthetic data; real-world feature distributions will differ.
- Sensitive to `transaction_amount` distribution shift (see Incident #011):
  when legitimate spending drifts upward, false positives rise.
