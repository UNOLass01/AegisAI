"""Phase 6 tests: scenario loading, scoring units, harness smoke run, results API."""
import importlib.util
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.agents.schemas import EvidenceItem, IncidentReport
from app.main import app
from app.rag.embeddings import clear_provider_cache, get_provider
from app.rag.ingest import ingest_knowledge
from app.rag.store import clear_client_cache, get_client
from app.services.logger import clear_log_buffer, log_buffer

REPO_ROOT = next(p for p in Path(__file__).resolve().parents
                 if (p / "evaluation" / "scenarios").is_dir())
SCENARIOS_DIR = REPO_ROOT / "evaluation" / "scenarios"


def _load_evaluation_module():
    spec = importlib.util.spec_from_file_location(
        "aegis_evaluation", REPO_ROOT / "evaluation" / "evaluation.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


ev = _load_evaluation_module()
client = TestClient(app)


@pytest.fixture()
def eval_env(monkeypatch):
    monkeypatch.setenv("EMBEDDING_PROVIDER", "hash")
    monkeypatch.setenv("QDRANT_URL", ":memory:")
    monkeypatch.setenv("LLM_PROVIDER", "stub")
    # Closed port: Prometheus error path without slow DNS timeouts.
    monkeypatch.setenv("PROMETHEUS_URL", "http://127.0.0.1:9")
    clear_provider_cache()
    clear_client_cache()
    yield
    clear_provider_cache()
    clear_client_cache()


def _report(**overrides) -> IncidentReport:
    base = {
        "investigation_id": "abc123",
        "status": "complete",
        "finding_summary": "precision dropped because of drift in amounts",
        "evidence": [
            EvidenceItem(tool="analyze_model", summary="precision drop details here",
                         source="ml/evaluation/reports/model_v2.json"),
            EvidenceItem(tool="get_metrics", summary="live precision v2=0.60 snapshot",
                         source="prometheus"),
            EvidenceItem(tool="search_knowledge", summary="matched incident writeup",
                         source="incidents/incident-011.md", score=0.7),
        ],
        "root_cause_hypothesis": "Data drift in transaction_amount",
        "confidence": 0.85,
        "recommended_actions": ["roll back", "monitor drift"],
    }
    base.update(overrides)
    return IncidentReport(**base)


# --- loading ---


def test_load_scenarios_returns_18_valid_definitions():
    scenarios = ev.load_scenarios(SCENARIOS_DIR)
    assert len(scenarios) == 18
    ids = [s["id"] for s in scenarios]
    assert len(set(ids)) == 18
    for scenario in scenarios:
        assert scenario["expected_root_cause"]["key"] in ev.KNOWN_KEYS
        assert set(scenario["expected_tools_used"]) == {
            "get_metrics", "analyze_logs", "analyze_model", "search_knowledge"}


def test_load_scenarios_rejects_empty_dir(tmp_path):
    with pytest.raises(ValueError):
        ev.load_scenarios(tmp_path)


# --- scoring units ---


def test_score_root_cause_key_match_and_keyword_fallback():
    expected = {"key": "data_drift", "keywords": ["drift", "transaction_amount"]}
    assert ev.score_root_cause("data_drift", "something else", expected) == 1.0
    assert ev.score_root_cause("labeling_error",
                               "Data drift in transaction_amount", expected) == 1.0
    assert ev.score_root_cause("labeling_error", "totally unrelated", expected) == 0.0


def test_score_tools_fractional():
    report = _report()
    assert ev.score_tools(report, ["analyze_model", "get_metrics"]) == 1.0
    assert ev.score_tools(report, ["analyze_model", "missing_tool"]) == 0.5


def test_score_grounding_flags_unsourced_items():
    good = _report()
    score, ungrounded = ev.score_grounding(good)
    assert score == 1.0 and ungrounded == []
    bad = _report(evidence=[
        EvidenceItem(tool="get_metrics", summary="x"),
        EvidenceItem(tool="search_knowledge", summary="a proper summary here",
                     source="incidents/i.md", score=0.5),
    ])
    score, ungrounded = ev.score_grounding(bad)
    assert score == 0.5 and len(ungrounded) == 1


def test_score_completeness_perfect_and_degraded():
    assert ev.score_completeness(_report()) == 1.0
    thin = _report(finding_summary="short", evidence=[], recommended_actions=[])
    assert ev.score_completeness(thin) < 1.0


# --- condition seeding ---


def test_apply_condition_seeds_spike_and_restores():
    clear_log_buffer()
    try:
        restore = ev.apply_condition({
            "type": "log_spike",
            "fast": {"n": 6, "latency_ms": 40.0,
                     "minutes_ago_start": 60, "minutes_ago_end": 30},
            "slow": {"n": 6, "latency_ms": 500.0,
                     "minutes_ago_start": 15, "minutes_ago_end": 0},
        })
        assert len(log_buffer) == 12
        from app.tools.log_analysis import analyze_logs
        findings = " | ".join(analyze_logs()["findings"])
        assert "latency spike" in findings
        restore()
        assert len(log_buffer) == 0
    finally:
        clear_log_buffer()


def test_apply_condition_rejects_unknown_type():
    with pytest.raises(ValueError):
        ev.apply_condition({"type": "nope"})


# --- harness smoke (2 scenarios end to end) ---


def test_run_harness_smoke_two_scenarios(eval_env):
    scenarios = ev.load_scenarios(SCENARIOS_DIR)
    subset = [s for s in scenarios if s["id"] in ("drift-01", "labels-01")]
    assert len(subset) == 2
    results = ev.run_harness(subset, ingest=True)
    assert results["n_scenarios"] == 2
    assert set(results["summary"]) == {
        "root_cause_accuracy", "tool_selection", "evidence_grounding",
        "report_completeness", "avg_latency_s", "avg_tokens"}
    by_id = {r["id"]: r for r in results["scenarios"]}
    assert by_id["drift-01"]["expected_root_cause"] == "data_drift"
    assert by_id["labels-01"]["expected_root_cause"] == "labeling_error"
    for row in results["scenarios"]:
        assert row["latency_s"] >= 0
        assert row["report_completeness"] == 1.0


# --- results endpoint ---


def test_evaluation_latest_roundtrip_and_404(tmp_path, monkeypatch):
    monkeypatch.setenv("EVALUATION_RESULTS_DIR", str(tmp_path))
    assert client.get("/evaluation/latest").status_code == 404
    payload = {"generated_at": "x", "n_scenarios": 1, "summary": {}, "scenarios": []}
    (tmp_path / "latest.json").write_text(json.dumps(payload))
    resp = client.get("/evaluation/latest")
    assert resp.status_code == 200
    assert resp.json()["n_scenarios"] == 1
