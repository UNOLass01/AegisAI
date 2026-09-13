"""Phase 7 tests: span tracing, cost model, trace persistence + API, agent metrics."""
import datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.agents import investigation_agent
from app.agents.investigation_agent import run_investigation
from app.agents.tracing import TRACED_STEPS, estimate_cost, make_span
from app.main import app
from app.models.agent_trace import AgentTrace
from app.models.base import Base
from app.rag.embeddings import clear_provider_cache, get_provider
from app.rag.ingest import ingest_knowledge
from app.rag.store import clear_client_cache, get_client
from app.services.database import get_db
from app.services.logger import clear_log_buffer
from app.tools import prometheus as prometheus_tool

client = TestClient(app)

V2_QUERY = "Why did fraud detection performance degrade after deployment v2?"


@pytest.fixture()
def rag_env(monkeypatch):
    monkeypatch.setenv("EMBEDDING_PROVIDER", "hash")
    monkeypatch.setenv("QDRANT_URL", ":memory:")
    monkeypatch.setenv("LLM_PROVIDER", "stub")
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


# --- cost model + span shape ---


def test_estimate_cost_known_unknown_and_free_models():
    assert estimate_cost("gpt-4o-mini", 1_000_000, 1_000_000) == 0.75
    assert estimate_cost("gpt-4o-mini", 1000, 500) == 0.00045
    assert estimate_cost("mystery-model", 10_000, 10_000) == 0.0
    assert estimate_cost("stub", 10_000, 10_000) == 0.0


def test_make_span_totals_tokens_and_carries_timing():
    span = make_span("reason", "2026-09-13T10:00:00+00:00", 12.5,
                     tokens_in=100, tokens_out=50, model="gpt-4o-mini")
    assert span["tokens"] == 150
    assert span["cost_usd"] == estimate_cost("gpt-4o-mini", 100, 50)
    assert span["status"] == "ok" and span["step"] == "reason"


# --- run spans ---


def test_run_records_all_seven_steps_in_order(rag_env, mock_prometheus, monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "stub")
    clear_log_buffer()
    try:
        report = run_investigation(V2_QUERY)
    finally:
        clear_log_buffer()
    spans = investigation_agent.last_run_info["spans"]
    assert {s["step"] for s in spans} == set(TRACED_STEPS)
    assert len(spans) == 7
    ordered = sorted(spans, key=lambda s: s["started_at"])
    assert ordered[0]["step"] == "investigate"
    for span in spans:
        assert span["duration_ms"] >= 0
        assert isinstance(span["tokens"], int)
        assert span["cost_usd"] >= 0
        assert span["status"] in ("ok", "error")
    assert report.investigation_id


def test_agent_metrics_exported_after_run(rag_env, mock_prometheus, monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "stub")
    clear_log_buffer()
    try:
        run_investigation(V2_QUERY)
    finally:
        clear_log_buffer()
    body = client.get("/metrics").text
    assert "agent_step_duration_seconds" in body
    assert "agent_tokens_total" in body
    assert "agent_cost_usd_total" in body


# --- persistence + trace API ---


def test_investigate_persists_trace_and_api_returns_timeline(
        rag_env, mock_prometheus, sqlite_db, monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "stub")
    clear_log_buffer()
    try:
        resp = client.post("/investigate", json={"query": V2_QUERY})
    finally:
        clear_log_buffer()
    assert resp.status_code == 200, resp.text
    investigation_id = resp.json()["investigation_id"]

    session = sqlite_db()
    try:
        rows = session.query(AgentTrace).filter(
            AgentTrace.investigation_id == investigation_id).all()
        assert len(rows) == 7
        assert {r.step for r in rows} == set(TRACED_STEPS)
    finally:
        session.close()

    trace = client.get(f"/investigations/{investigation_id}/trace")
    assert trace.status_code == 200
    body = trace.json()
    assert body["investigation_id"] == investigation_id
    assert [s["step"] for s in body["spans"]].count("investigate") == 1
    assert len(body["spans"]) == 7
    timestamps = [s["timestamp"] for s in body["spans"]]
    assert timestamps == sorted(timestamps)
    for span in body["spans"]:
        assert {"step", "duration_ms", "tokens", "cost_usd",
                "timestamp"} <= set(span)
        datetime.datetime.fromisoformat(span["timestamp"])


def test_trace_api_404_for_unknown_investigation(sqlite_db):
    assert client.get("/investigations/doesnotexist/trace").status_code == 404


def test_agent_trace_model_roundtrip(sqlite_db):
    session = sqlite_db()
    try:
        session.add(AgentTrace(investigation_id="abc", step="reason",
                               duration_ms=12.5, tokens=150, cost_usd=0.0001,
                               timestamp=datetime.datetime.now(datetime.timezone.utc)))
        session.commit()
        row = session.query(AgentTrace).filter_by(investigation_id="abc").one()
        assert (row.step, row.tokens) == ("reason", 150)
    finally:
        session.close()
