# Incident #014: labeling-pipeline error destroyed recall

- **Date:** 2026-09-06
- **Severity:** high
- **Model:** v3
- **Symptom:** recall collapsed 0.665 → 0.413 after the v3 deployment; fraud
  slipped through while dashboards still looked "green" on accuracy (0.942).

## Summary

Why did recall collapse? Recall collapsed because a backfill job flipped 30%
of fraud training labels to legitimate, so the v3 model learned fraud patterns
as normal and stopped flagging them. False negatives nearly doubled (50 → 98).

## Timeline

1. A backfill job mis-mapped the fraud-label column, flipping 30% of fraud
   labels to legitimate in the training export.
2. v3 trained on the corrupted labels and passed the accuracy gate.
3. Chargebacks spiked: false negatives nearly doubled (50 → 98).

## Root cause

Label noise in training, not drift and not model code. With a third of fraud
examples labeled legitimate, the classifier learned that fraud patterns are
"normal" and stopped flagging them.

## Evidence

- `ml/evaluation/reports/model_v3.json`: recall 0.4132, FN=98 vs v1 FN=50.
- Precision misleadingly rose (0.740 → 0.793) because the model under-predicts.
- Training-export audit showed 30% fraud-label flip rate for the v3 window.

## Resolution & recommended actions

1. Roll back to v1; quarantine the corrupted training export.
2. Add a label-distribution check to the training pipeline (fraud-rate guard).
3. Gate promotions on recall, not accuracy, for fraud models.
4. Keep per-version training-data manifests so bad exports are traceable.
