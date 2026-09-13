# Experiment: v1 clean baseline

- **Config:** 5000 training rows (seed 100), 2000 test rows (seed 200), no shifts, no flips
- **Result:** accuracy 0.9525, precision 0.7400, recall 0.6647, F1 0.7000
- **Note:** amount is the dominant signal; night hours and electronics/travel
  categories add a smaller boost. This is the reference every later version is
  compared against. Artifact: `ml/models/model_v1.pkl`.
