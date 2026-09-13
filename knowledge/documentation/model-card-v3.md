# Model Card — Fraud Detection v3 (label-noise)

- **Version:** v3
- **Status:** degraded — do NOT promote (see Incident #014)
- **Model:** same RandomForest pipeline as v1, trained on mislabeled data
- **Training data:** `synthetic-clean-v1` with 30% of fraud labels flipped to
  legitimate (labeling-pipeline bug), 5000 rows, seed 100
- **Eval data:** `synthetic-clean-v1` — 2000 rows, seed 200

## Metrics (held-out)

| accuracy | precision | recall | F1 |
|---|---|---|---|
| 0.9420 | 0.7931 | 0.4132 | 0.5433 |

Confusion: TP=69, FP=18, TN=1815, FN=98 (n=2000).

## What changed vs v1

Recall collapsed 0.665 → 0.413 while precision rose slightly (0.740 → 0.793).
The model rarely flags fraud now, so when it does flag it is usually right —
but it misses most fraud (false negatives nearly doubled, 50 → 98).

## Limitations

- Unacceptable miss rate for a fraud product.
- High precision here is misleading: it comes from under-predicting, not from
  better discrimination. Always read precision together with recall.
