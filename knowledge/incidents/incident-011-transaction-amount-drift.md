# Incident #011: transaction_amount drift caused FP spike

- **Date:** 2026-09-02
- **Severity:** high
- **Model:** v2 (retrained on drifted data)
- **Symptom:** precision dropped 0.740 → 0.603 after the v2 deployment; the
  review queue filled with false positives (FP 42 → 58 on the held-out set).

## Summary

Why did precision drop? Precision dropped because legitimate
`transaction_amount` values drifted +30% into the range the model associated
with fraud, so ordinary purchases started scoring as fraud and false positives
spiked. Retraining on the drifted data (v2) did not restore precision.

## Timeline

1. Holiday season pushed legitimate `transaction_amount` up ~30%.
2. The team retrained on the drifted data and shipped v2.
3. Precision kept dropping in production; reviewers reported obvious
   legitimate purchases flagged as fraud.

## Root cause

Data drift, not model code. Legitimate spending moved into the amount range
the model associated with fraud, so the classifier's amount threshold no
longer separated the classes. Retraining on drifted data baked the overlap in
instead of fixing it.

## Evidence

- `ml/evaluation/reports/model_v2.json`: precision 0.6027, FP=58 vs v1 FP=42.
- Grafana precision-proxy panel (true positives / flagged) fell from ~0.8 to
  ~0.5 during the incident replay.
- `transaction_amount` distribution of legitimate traffic shifted +30% vs the
  v1 training baseline.

## Resolution & recommended actions

1. Roll back to v1 while legitimate spending is elevated.
2. Add a distribution-drift monitor on `transaction_amount` (e.g. PSI weekly).
3. Recalibrate the decision threshold per regime instead of blind retraining.
4. Never retrain on unreviewed drifted data without a holdout comparison.
