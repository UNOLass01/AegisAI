# Incident #009: night-traffic load spike raised p95 latency

- **Date:** 2026-08-28
- **Severity:** medium
- **Model:** v1 (model was healthy; this was infra, not ML)
- **Affected:** /predict latency
- **Status:** resolved
- **Symptom:** `/predict` p95 latency jumped 0.05s → 0.46s during a traffic
  surge; no 5xx errors, but the Grafana latency panel paged the on-call.

## Summary

Why did latency spike? Latency spiked because replay traffic ran at 8x
concurrency against a single backend replica, queueing `/predict` requests.
Precision and error rate never moved — this was infra overload, not model
degradation.

## Timeline

1. Evening traffic replayed at 8x concurrency against a single backend replica.
2. Request rate on `/predict` rose ~1.4 → ~3.9 req/s.
3. p95 latency climbed while precision and error rate stayed flat.

## Root cause

Concurrency overload on one uvicorn worker set, not model degradation. The
model metrics (precision proxy ~0.8) never moved, which ruled out ML causes
within minutes.

## Evidence

- Grafana "predict latency p95 by model version" panel: v1 p95 0.05 → 0.46s.
- Request-rate panel showed the concurrency surge on `/predict`.
- Structured logs (`latency_ms` per request) confirmed queueing, not slow models.

## Resolution & recommended actions

1. Throttle replay concurrency; add horizontal replicas for peak windows.
2. Keep latency alerts separate from precision alerts to avoid ML blame.
3. Load-test before doubling replay traffic again.
