"""Phase 5 tests: tools, LLM abstraction, agent graph, /investigate endpoint.

LLM-dependent paths use LLM_PROVIDER=stub (deterministic) or monkeypatched
HTTP. Prometheus is monkeypatched with canned series. Qdrant uses :memory:
with the hash embedding provider.
"""
import datetime
import json

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.agents import investigation_agent
from app.agents import llm as llm_module
from app.agents.investigation_agent import (
    _validate_llm_reasoning,
    extract_versions,
    run_investigation,
)
from app.agents.schemas import IncidentReport
from app.main import app
from app.models.base import Base
from app.models.investigation import Investigation
from app.rag.embeddings import clear_provider_cache, get_provider
from app.rag.ingest import ingest_knowledge
from app.rag.store import clear_client_cache, get_client
from app.services.database import get_db
from app.services.logger import clear_log_buffer, record_log_entry
from app.tools import knowledge_search as knowledge_tool
from app.tools import log_analysis as logs_tool
from app.tools import model_analysis as model_tool
from app.tools import prometheus as prometheus_tool
from app.tools import report as report_tool

client = TestClient(app)

V2_QUERY = "Why did fraud detection performance degrade after deployment v2?"


@pytest.fixture()
def rag_env(monkeypatch):
    monkeypatch.setenv("EMBEDDING_PROVIDER", "hash")
    monkeypatch.setenv("QDRANT_URL", ":memory:")
    monkeypatch.setenv("LLM_PROVIDER", "stub")
    # Closed port: Prometheus error path without slow DNS timeouts.
    monkeypatch.setenv("PROMETHEUS_URL", "http://127.0.0.1:9")
    clear_provider_cache()
    clear_client_cache()
    mem = get_client(url=":memory:")
    ingest_knowledge(client=mem, provider=get_provider("hash"))
    yield mem
    clear_provider_cache()
    clear_client_cache()


@pytest.fixture()
def mock_prometheus(monkeypatch):
    def fake_query(expr: str):
        if "true_positives" in expr:
            return [
                {"metric": {"model_version": "v1"}, "value": [0, "0.8"]},
                {"metric": {"model_version": "v2"}, "value": [0, "0.6"]},
            ]
        if "aegis_predict_latency_seconds" in expr:
            return [
                {"metric": {"model_version": "v1"}, "value": [0, "0.05"]},
                {"metric": {"model_version": "v2"}, "value": [0, "0.45"]},
            ]
        if "aegis_predict_requests_total" in expr:
            return [
                {"metric": {"model_version": "v1"}, "value": [0, "1.5"]},
                {"metric": {"model_version": "v2"}, "value": [0, "2.0"]},
            ]
        if "5.." in expr:
            return [{"metric": {}, "value": [0, "0.001"]}]
        return [{"metric": {"handler": "/predict"}, "value": [0, "3.5"]}]

    monkeypatch.setattr(prometheus_tool, "prom_query", fake_query)


@pytest.fixture()
def sqlite_db():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)

    def override():
        db = factory()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override
    yield factory
    app.dependency_overrides.pop(get_db, None)


def _log_entry(minutes_ago: float, latency_ms: float, status: int,
               endpoint: str = "/predict", version: str = "v1") -> dict:
    ts = (datetime.datetime.now(datetime.timezone.utc)
          - datetime.timedelta(minutes=minutes_ago)).isoformat()
    return {"timestamp": ts, "endpoint": endpoint, "method": "POST",
            "model_version": version, "latency_ms": latency_ms,
            "status_code": status}


# --- model tool ---


def test_analyze_model_v2_reports_precision_drop_and_fp_rise():
    result = model_tool.analyze_model("v2")
    assert result["version"] == "v2" and result["baseline_version"] == "v1"
    assert result["deltas"]["precision"] < -0.05
    assert result["deltas"]["false_positives"] > 0
    text = " | ".join(result["flags"])
    assert "precision drop" in text and "false positives rose" in text


def test_analyze_model_v3_reports_recall_drop():
    result = model_tool.analyze_model("v3")
    assert "recall drop" in " | ".join(result["flags"])


def test_analyze_model_defaults_to_latest_and_rejects_unknown():
    assert model_tool.analyze_model()["version"] == "v3"
    assert "error" in model_tool.analyze_model("v99")


# --- prometheus tool ---


def test_get_metrics_parses_canned_series(mock_prometheus):
    result = prometheus_tool.get_metrics()
    assert result["precision_by_version"] == {"v1": 0.8, "v2": 0.6}
    assert result["p95_latency_s_by_version"] == {"v1": 0.05, "v2": 0.45}
    assert result["error_share_5xx"] == 0.001


def test_get_metrics_focus_version_narrows_panels(mock_prometheus):
    result = prometheus_tool.get_metrics(model_version="v2")
    assert result["precision_by_version"] == {"v2": 0.6}
    assert result["focus_version"] == "v2"


def test_get_metrics_focus_version_without_traffic_yields_empty_panels(
        mock_prometheus, monkeypatch):
    def only_v1(expr: str):
        if "5.." in expr:
            return []
        if "aegis_predict" in expr:
            return [{"metric": {"model_version": "v1"}, "value": [0, "0.8"]}]
        return [{"metric": {"handler": "/predict"}, "value": [0, "1.0"]}]

    monkeypatch.setattr(prometheus_tool, "prom_query", only_v1)
    result = prometheus_tool.get_metrics(model_version="v2")
    assert result["precision_by_version"] == {}
    assert result["request_volume_by_version"] == {}
    # Report composition must not crash on the empty panels.
    evidence = report_tool._metrics_evidence(result)
    assert "no live traffic" in evidence.summary


def test_get_metrics_reports_error_when_prometheus_down(monkeypatch):
    def boom(expr: str):
        raise ConnectionError("down")

    monkeypatch.setattr(prometheus_tool, "prom_query", boom)
    result = prometheus_tool.get_metrics()
    assert "error" in result and result["tool"] == "get_metrics"


# --- logs tool ---


def test_parse_time_range_valid_and_invalid():
    assert logs_tool.parse_time_range(None) is None
    assert logs_tool.parse_time_range("15m") == datetime.timedelta(minutes=15)
    with pytest.raises(ValueError):
        logs_tool.parse_time_range("bogus")


def test_analyze_logs_quiet_traffic_has_no_anomalies():
    clear_log_buffer()
    try:
        for i in range(12):
            record_log_entry(_log_entry(minutes_ago=i, latency_ms=40.0, status=200))
        result = logs_tool.analyze_logs()
        assert result["requests"] == 12
        assert result["error_rate_5xx"] == 0.0
        assert any("no anomalies" in f for f in result["findings"])
    finally:
        clear_log_buffer()


def test_analyze_logs_detects_latency_and_error_spikes():
    clear_log_buffer()
    try:
        for i in range(60, 30, -1):  # older half: fast + clean
            record_log_entry(_log_entry(minutes_ago=i, latency_ms=40.0, status=200))
        for i in range(30, 0, -1):  # recent half: slow + errors
            status = 500 if i % 3 == 0 else 200
            record_log_entry(_log_entry(minutes_ago=i, latency_ms=400.0, status=status))
        result = logs_tool.analyze_logs()
        text = " | ".join(result["findings"])
        assert "latency spike" in text
        assert "error spike" in text
        assert result["model_mix"] == {"v1": 60}
    finally:
        clear_log_buffer()


def test_analyze_logs_window_filtering():
    clear_log_buffer()
    try:
        record_log_entry(_log_entry(minutes_ago=120, latency_ms=40.0, status=200))
        record_log_entry(_log_entry(minutes_ago=5, latency_ms=40.0, status=200))
        assert logs_tool.analyze_logs(time_range="15m")["requests"] == 1
        assert logs_tool.analyze_logs()["requests"] == 2
    finally:
        clear_log_buffer()


# --- knowledge tool ---


def test_search_knowledge_returns_attributed_hits(rag_env):
    result = knowledge_tool.search_knowledge(
        "incident 011 false positives transaction amount drift", client=rag_env)
    assert result["tool"] == "search_knowledge"
    assert "incident-011" in result["hits"][0]["source"]
    assert set(result["hits"][0]) >= {"source", "title", "incident_id", "score", "excerpt"}


# --- LLM abstraction ---


def test_resolve_llm_stub_explicit_and_auto_without_key(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "stub")
    assert llm_module.resolve_llm().kind == "stub"
    monkeypatch.setenv("LLM_PROVIDER", "auto")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    assert llm_module.resolve_llm().kind == "stub"


def test_resolve_llm_openai_and_ollama(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "openai")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("LLM_MODEL", "gpt-4o-mini")
    config = llm_module.resolve_llm()
    assert (config.kind, config.model) == ("openai", "gpt-4o-mini")
    assert config.base_url == "https://api.openai.com/v1"
    monkeypatch.setenv("LLM_PROVIDER", "ollama")
    config = llm_module.resolve_llm()
    assert config.base_url == "http://localhost:11434/v1"


def test_complete_posts_openai_compatible_body(monkeypatch):
    captured = {}

    class FakeResp:
        def raise_for_status(self):
            pass

        def json(self):
            return {"choices": [{"message": {"content": "hello"}}]}

    def fake_post(url, headers, json, timeout):
        captured.update(url=url, headers=headers, json=json)
        return FakeResp()

    monkeypatch.setattr(llm_module.httpx, "post", fake_post)
    config = llm_module.LLMConfig("openai", "https://x/v1", "sk-test", "m")
    assert llm_module.complete(config, [{"role": "user", "content": "hi"}],
                               json_mode=True) == "hello"
    assert captured["url"] == "https://x/v1/chat/completions"
    assert captured["headers"]["Authorization"] == "Bearer sk-test"
    assert captured["json"]["response_format"] == {"type": "json_object"}


def test_complete_refuses_stub_and_try_complete_json_swallows_errors(monkeypatch):
    with pytest.raises(RuntimeError):
        llm_module.complete(llm_module.LLMConfig("stub", None, None, "stub"), [])
    monkeypatch.setenv("LLM_PROVIDER", "stub")
    assert llm_module.try_complete_json(
        llm_module.resolve_llm(), []) is None


# --- graph ---


def test_extract_versions():
    assert extract_versions("degrade after deployment v2?") == ["v2"]
    assert extract_versions("compare v1 v2 v3") == ["v1", "v2", "v3"]
    assert extract_versions("general slowness") == []
    # First mentioned version is the investigation subject.
    assert investigation_agent._focus_version({"focus_versions": ["v3", "v2"]}) == "v3"
    assert investigation_agent._focus_version({"focus_versions": []}) is None


def test_validate_llm_reasoning_accepts_good_rejects_bad():
    good = {"root_cause_hypothesis": "drift", "confidence": 0.8,
            "finding_summary": "s", "recommended_actions": ["a"]}
    assert _validate_llm_reasoning(good)["confidence"] == 0.8
    assert _validate_llm_reasoning({**good, "confidence": 2.0}) == {}
    assert _validate_llm_reasoning({**good, "recommended_actions": []}) == {}
    assert _validate_llm_reasoning("nope") == {}


def test_run_investigation_identifies_drift_with_grounded_evidence(
        rag_env, mock_prometheus, monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "stub")
    clear_log_buffer()
    try:
        report = run_investigation(V2_QUERY)
    finally:
        clear_log_buffer()
    assert isinstance(report, IncidentReport)
    assert "drift" in report.root_cause_hypothesis.lower()
    assert report.confidence >= 0.6
    assert report.status == "complete" and report.investigation_id
    tools = {e.tool for e in report.evidence}
    assert {"analyze_model", "get_metrics", "analyze_logs",
            "search_knowledge"} <= tools
    assert any("incident-011" in (e.source or "") for e in report.evidence)
    assert len(report.recommended_actions) >= 2


def test_reason_node_uses_llm_when_configured(rag_env, mock_prometheus, monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "openai")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")

    class FakeResp:
        def raise_for_status(self):
            pass

        def json(self):
            return {"choices": [{"message": {"content": json.dumps(
                {"root_cause_hypothesis": "LLM says drift",
                 "confidence": 0.77,
                 "finding_summary": "synthesized",
                 "recommended_actions": ["act one", "act two"]})}}]}

    monkeypatch.setattr(llm_module.httpx, "post",
                        lambda *a, **k: FakeResp())
    report = run_investigation(V2_QUERY)
    assert report.root_cause_hypothesis == "LLM says drift"
    assert report.confidence == 0.77
    # Evidence still comes from tools, not the LLM.
    assert any(e.tool == "analyze_model" for e in report.evidence)


# --- endpoint ---


def test_investigate_persists_report_to_db(rag_env, mock_prometheus, sqlite_db,
                                           monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "stub")
    clear_log_buffer()
    try:
        resp = client.post("/investigate", json={"query": V2_QUERY})
    finally:
        clear_log_buffer()
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert "drift" in body["root_cause_hypothesis"].lower()
    session = sqlite_db()
    try:
        rows = session.query(Investigation).all()
        assert len(rows) == 1
        assert rows[0].query == V2_QUERY
        assert rows[0].status == "complete"
        assert rows[0].confidence == body["confidence"]
        stored = rows[0].report_json
        assert stored["investigation_id"] == body["investigation_id"]
        assert len(stored["evidence"]) >= 4
    finally:
        session.close()


def test_investigate_validates_input(sqlite_db):
    assert client.post("/investigate", json={"query": "x"}).status_code == 422
    assert client.post(
        "/investigate", json={"query": V2_QUERY, "time_range": "bogus"}
    ).status_code == 422


def test_decide_root_cause_labeling_scenario():
    model = {"version": "v3", "baseline_version": "v2",
             "metrics": {"dataset_version": "synthetic-clean-v1"},
             "flags": ["recall drop 0.66 -> 0.41",
                       "false negatives rose 50 -> 98"],
             "deltas": {}}
    knowledge = {"hits": [{"source": "incidents/incident-014.md",
                           "title": "Incident #014", "incident_id": "014",
                           "score": 0.7, "excerpt": ""}]}
    key, confidence, signals, _ = report_tool.decide_root_cause(
        model, {"precision_by_version": {}}, {"findings": []}, knowledge)
    assert key == "labeling_error" and confidence >= 0.6
