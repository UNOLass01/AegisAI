"""Phase 3 tests: metrics endpoint, version counters, JSON logs, simulator units,
dashboard/prometheus config cross-checks."""
import importlib.util
import io
import json
import logging
import re
from contextlib import contextmanager
from pathlib import Path

import yaml
from fastapi.testclient import TestClient
from prometheus_client import REGISTRY

from app.main import app
from app.services.logger import JsonFormatter, get_logger, log_request

def _find_repo_root() -> Path:
    """Nearest ancestor containing monitoring/ (repo root locally, /code in Docker)."""
    for ancestor in Path(__file__).resolve().parents:
        if (ancestor / "monitoring" / "simulate_incident.py").exists():
            return ancestor
    raise FileNotFoundError("repo root with monitoring/simulate_incident.py not found")


REPO_ROOT = _find_repo_root()

client = TestClient(app)

KNOWN_METRICS = {
    "http_requests_total",
    "http_request_duration_seconds",
    "http_request_duration_highr_seconds",
    "aegis_predict_requests_total",
    "aegis_predict_latency_seconds",
    "aegis_predict_correct_total",
    "aegis_predict_flagged_total",
    "aegis_predict_true_positives_total",
}


def _load_simulator():
    path = REPO_ROOT / "monitoring" / "simulate_incident.py"
    spec = importlib.util.spec_from_file_location("simulate_incident", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


sim = _load_simulator()


# --- /metrics ---


def test_metrics_endpoint_exposes_standard_and_custom_metrics():
    resp = client.get("/metrics")
    assert resp.status_code == 200
    body = resp.text
    for metric in KNOWN_METRICS:
        assert metric in body, f"{metric} missing from /metrics"


def test_predict_increments_per_version_counters():
    before = REGISTRY.get_sample_value(
        "aegis_predict_requests_total", {"model_version": "v1"}
    ) or 0.0
    resp = client.post(
        "/predict",
        json={
            "transaction_amount": 50.0,
            "merchant_category": "grocery",
            "hour_of_day": 12,
            "model_version": "v1",
            "ground_truth": True,
        },
    )
    assert resp.status_code == 200
    after = REGISTRY.get_sample_value(
        "aegis_predict_requests_total", {"model_version": "v1"}
    )
    assert after == before + 1


def test_correct_counter_only_counts_matches():
    correct_before = REGISTRY.get_sample_value(
        "aegis_predict_correct_total", {"model_version": "v2"}
    ) or 0.0
    total_before = REGISTRY.get_sample_value(
        "aegis_predict_requests_total", {"model_version": "v2"}
    ) or 0.0
    # Obvious fraud predicted as fraud with matching ground truth -> correct +1.
    client.post(
        "/predict",
        json={
            "transaction_amount": 900.0,
            "merchant_category": "electronics",
            "hour_of_day": 3,
            "model_version": "v2",
            "ground_truth": True,
        },
    )
    # Obvious legit with deliberately wrong ground truth -> correct unchanged.
    client.post(
        "/predict",
        json={
            "transaction_amount": 12.5,
            "merchant_category": "grocery",
            "hour_of_day": 13,
            "model_version": "v2",
            "ground_truth": True,
        },
    )
    correct_after = REGISTRY.get_sample_value(
        "aegis_predict_correct_total", {"model_version": "v2"}
    )
    total_after = REGISTRY.get_sample_value(
        "aegis_predict_requests_total", {"model_version": "v2"}
    )
    assert total_after == total_before + 2
    assert correct_after == correct_before + 1


def test_flagged_and_true_positive_counters_track_precision_inputs():
    flagged_before = REGISTRY.get_sample_value(
        "aegis_predict_flagged_total", {"model_version": "v1"}
    ) or 0.0
    tp_before = REGISTRY.get_sample_value(
        "aegis_predict_true_positives_total", {"model_version": "v1"}
    ) or 0.0
    # Obvious fraud, matching ground truth -> flagged +1, TP +1.
    client.post(
        "/predict",
        json={
            "transaction_amount": 900.0,
            "merchant_category": "electronics",
            "hour_of_day": 3,
            "model_version": "v1",
            "ground_truth": True,
        },
    )
    # Obvious legit -> flagged/TP unchanged.
    client.post(
        "/predict",
        json={
            "transaction_amount": 12.5,
            "merchant_category": "grocery",
            "hour_of_day": 13,
            "model_version": "v1",
            "ground_truth": False,
        },
    )
    flagged_after = REGISTRY.get_sample_value(
        "aegis_predict_flagged_total", {"model_version": "v1"}
    )
    tp_after = REGISTRY.get_sample_value(
        "aegis_predict_true_positives_total", {"model_version": "v1"}
    )
    assert flagged_after == flagged_before + 1
    assert tp_after == tp_before + 1


# --- structured JSON logs ---


@contextmanager
def _capture_records():
    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    handler.setFormatter(JsonFormatter())
    logger = get_logger("aegis")
    logger.addHandler(handler)
    try:
        yield stream
    finally:
        logger.removeHandler(handler)


def _read_records(stream: io.StringIO) -> list[dict]:
    return [json.loads(line) for line in stream.getvalue().splitlines() if line.strip()]


def test_request_logs_are_structured_json_with_required_keys():
    with _capture_records() as stream:
        client.get("/health")
        client.post(
            "/predict",
            json={
                "transaction_amount": 50.0,
                "merchant_category": "fuel",
                "hour_of_day": 9,
                "model_version": "v2",
            },
        )
    records = _read_records(stream)
    by_endpoint = {r.get("endpoint"): r for r in records if "endpoint" in r}
    assert "/health" in by_endpoint
    assert "/predict" in by_endpoint
    for endpoint, record in by_endpoint.items():
        for key in ("timestamp", "level", "endpoint", "model_version",
                    "latency_ms", "status_code"):
            assert key in record, f"{endpoint} log missing {key}"
    assert by_endpoint["/health"]["model_version"] is None
    assert by_endpoint["/health"]["status_code"] == 200
    assert by_endpoint["/predict"]["model_version"] == "v2"
    assert isinstance(by_endpoint["/predict"]["latency_ms"], (int, float))


def test_metrics_endpoint_is_not_logged():
    with _capture_records() as stream:
        client.get("/metrics")
    endpoints = [r.get("endpoint") for r in _read_records(stream)]
    assert "/metrics" not in endpoints


def test_log_request_unit_emits_required_keys():
    stream = io.StringIO()
    logger = logging.getLogger("aegis-test-unit")
    logger.handlers.clear()
    logger.setLevel(logging.INFO)
    logger.addHandler(logging.StreamHandler(stream))
    logger.handlers[0].setFormatter(JsonFormatter())
    log_request(logger, endpoint="/predict", method="POST", status_code=200,
                latency_ms=12.5, model_version="v1")
    record = json.loads(stream.getvalue().strip())
    assert record["endpoint"] == "/predict"
    assert record["model_version"] == "v1"
    assert record["latency_ms"] == 12.5
    assert record["status_code"] == 200
    assert "timestamp" in record and "level" in record


# --- simulator units (no network) ---


def test_build_payload_carries_features_and_ground_truth():
    row = {"transaction_amount": 42.5, "merchant_category": "fuel",
           "hour_of_day": 18, "is_fraud": 1}
    payload = sim.build_payload(row, "v1")
    assert payload == {
        "transaction_amount": 42.5,
        "merchant_category": "fuel",
        "hour_of_day": 18,
        "model_version": "v1",
        "ground_truth": True,
    }


def test_run_phase_stats_with_fake_sender():
    payloads = [
        {"ground_truth": True},
        {"ground_truth": False},
        {"ground_truth": True},
    ]

    def always_right(_base_url, payload):
        return 200, {"is_fraud": payload["ground_truth"]}, 0.005

    stats = sim.run_phase("http://unused", payloads, max_workers=2, sender=always_right)
    assert stats["n"] == 3 and stats["ok"] == 3 and stats["correct"] == 3
    assert stats["precision_proxy"] == 1.0 and stats["avg_latency_ms"] == 5.0
    # always_right echoes each ground truth (True, False, True),
    # so flagged = 2, TP = 2, precision 1.0.
    assert stats["flagged"] == 2 and stats["true_positives"] == 2
    assert stats["precision"] == 1.0

    def always_wrong(_base_url, payload):
        return 200, {"is_fraud": not payload["ground_truth"]}, 0.002

    stats = sim.run_phase("http://unused", payloads, max_workers=1, sender=always_wrong)
    assert stats["ok"] == 3 and stats["correct"] == 0 and stats["precision_proxy"] == 0.0
    # Inverted predictions flag the single legit payload; it is not a TP.
    assert stats["flagged"] == 1 and stats["true_positives"] == 0
    assert stats["precision"] == 0.0


def test_run_phase_counts_non_200_as_not_ok():
    def failing(_base_url, _payload):
        return 500, {}, 0.001

    stats = sim.run_phase("http://unused", [{"ground_truth": True}], sender=failing)
    assert stats["ok"] == 0 and stats["correct"] == 0


# --- config cross-checks ---


def _dashboard_exprs() -> list[str]:
    path = REPO_ROOT / "monitoring" / "grafana" / "dashboards" / "aegis-overview.json"
    dashboard = json.loads(path.read_text())
    assert dashboard["title"] == "AegisAI Overview"
    assert len(dashboard["panels"]) >= 6
    return [t["expr"] for p in dashboard["panels"] for t in p["targets"]]


def test_dashboard_queries_reference_only_known_metrics():
    promql_keywords = {"sum", "by", "rate", "histogram_quantile", "or", "vector", "on"}
    label_names = {"le", "handler", "model_version", "status", "method"}
    for expr in _dashboard_exprs():
        scrubbed = re.sub(r"\[[^\]]*\]", "", expr)  # range selectors like [2m]
        scrubbed = re.sub(r'"[^"]*"', "", scrubbed)  # matchers like status=~"5.."
        tokens = set(re.findall(r"[a-z_][a-z0-9_]*", scrubbed))
        for token in tokens - promql_keywords - label_names:
            normalized = re.sub(r"(_bucket|_count|_sum|_created)$", "", token)
            assert normalized in KNOWN_METRICS, f"unknown metric {token!r} in {expr!r}"


def test_dashboard_metrics_exist_on_metrics_endpoint():
    body = client.get("/metrics").text
    for metric in KNOWN_METRICS:
        assert metric in body


def test_prometheus_config_targets_backend():
    config = yaml.safe_load(
        (REPO_ROOT / "monitoring" / "prometheus" / "prometheus.yml").read_text()
    )
    targets = [t for job in config["scrape_configs"]
               for sc in job["static_configs"] for t in sc["targets"]]
    assert "backend:8000" in targets
