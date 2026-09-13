# Experiment: v3 training with 30% fraud-label flips

- **Config:** same as v1 but 30% of fraud training labels flipped to legitimate.
- **Result:** accuracy 0.9420, precision 0.7931, recall 0.4132, F1 0.5433
- **Note:** the model learned fraud patterns as "normal" and stopped flagging:
  FN 50 → 98. Precision rose only because volume collapsed — a textbook case of
  why accuracy/precision alone must not gate fraud models. See Incident #014.
  Artifact: `ml/models/model_v3.pkl`.
