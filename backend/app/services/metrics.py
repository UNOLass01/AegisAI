"""Prometheus metrics for the AegisAI backend.

Standard HTTP metrics (request count, latency histogram, status codes) come
from ``prometheus_fastapi_instrumentator`` (wired in ``app.main``). The
counters/histograms below add model-level observability:

- ``aegis_predict_requests_total{model_version}`` — prediction volume by version
  (powers the "model version in use" Grafana panel).
- ``aegis_predict_latency_seconds{model_version}`` — per-version latency.
- ``aegis_predict_correct_total{model_version}`` — predictions matching the
  caller-supplied ``ground_truth`` (demo harness only); the ratio
  correct/requests is the precision-proxy panel.
"""
from prometheus_client import Counter, Histogram

PREDICT_REQUESTS = Counter(
    "aegis_predict_requests_total",
    "Total /predict requests by model version.",
    ["model_version"],
)
PREDICT_LATENCY = Histogram(
    "aegis_predict_latency_seconds",
    "/predict request latency in seconds by model version.",
    ["model_version"],
)
PREDICT_CORRECT = Counter(
    "aegis_predict_correct_total",
    "Predictions matching caller-supplied ground truth, by model version.",
    ["model_version"],
)
PREDICT_FLAGGED = Counter(
    "aegis_predict_flagged_total",
    "Predictions flagged as fraud, by model version.",
    ["model_version"],
)
PREDICT_TRUE_POSITIVES = Counter(
    "aegis_predict_true_positives_total",
    "Flagged predictions with caller-supplied ground truth true, by version.",
    ["model_version"],
)
