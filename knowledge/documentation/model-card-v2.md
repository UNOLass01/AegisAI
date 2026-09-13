# Model Card — Fraud Detection v2 (drift-retrained)

- **Version:** v2
- **Status:** degraded — do NOT promote without drift mitigation (see Incident #011)
- **Model:** same RandomForest pipeline as v1, retrained on drifted data
- **Training data:** `synthetic-drifted-amount-plus30pct-v1` — 5000 rows, seed 100,
  legitimate `transaction_amount` shifted +30% (holiday spending surge)
- **Eval data:** `synthetic-drifted-amount-plus30pct-v1` — 2000 rows, seed 200

## Metrics (held-out, under drift)

| accuracy | precision | recall | F1 |
|---|---|---|---|
| 0.9315 | 0.6027 | 0.5269 | 0.5623 |

Confusion: TP=88, FP=58, TN=1775, FN=79 (n=2000).

## What changed vs v1

Precision dropped 0.740 → 0.603 and false positives rose 42 → 58. Legitimate
transactions now look like historical fraud because the amount distribution
shifted. Retraining on the drifted data did NOT fix the problem — the class
overlap is genuinely worse.

## Limitations

- Lower precision means more review workload per caught fraud.
- Recall also fell (0.665 → 0.527): the model is worse in both directions.
- Root cause is data drift, not model capacity; prefer drift detection and
  threshold recalibration over blind retraining.
