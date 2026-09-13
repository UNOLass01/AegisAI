# Experiment: v2 retrain on drifted data

- **Config:** same as v1 but legitimate `transaction_amount` × 1.30 in training;
  evaluated under the same +30% drift.
- **Result:** accuracy 0.9315, precision 0.6027, recall 0.5269, F1 0.5623
- **Note:** retraining adapted the threshold but could not recover separability:
  FP rose 42 → 58 and recall fell too. Conclusion: the drift, not the training
  procedure, is the problem — see Incident #011. Artifact: `ml/models/model_v2.pkl`.
