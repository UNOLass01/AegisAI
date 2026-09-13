"""Phase 8 backend tests: incidents, investigations list/detail, system summary."""
import datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api import incidents as incidents_api
from app.main import app
from app.models.agent_trace import AgentTrace
from app.models.base import Base
from app.models.investigation import Investigation
from app.services.database import get_db
from app.tools import prometheus as prometheus_tool

client = TestClient(app)


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


def _seed_investigation(session, query="Why did v2 degrade?", hex_id="hex123"):
    row = Investigation(
        query=query, status="complete", root_cause="Data drift",
        confidence=0.9,
        report_json={"investigation_id": hex_id,
                     "evidence": [{"tool": "analyze_model"}]})
    session.add(row)
    session.commit()
    session.refresh(row)
    session.add(AgentTrace(
        investigation_id=hex_id, step="reason", duration_ms=1.5,
        tokens=0, cost_usd=0.0,
        timestamp=datetime.datetime.now(datetime.timezone.utc)))
    session.commit()
    return row


# --- incidents ---


def test_list_incidents_returns_three_attributed_rows():
    resp = client.get("/incidents")
    assert resp.status_code == 200, resp.text
    rows = {r["id"]: r for r in resp.json()}
    assert {"009", "011", "014"} <= set(rows)
    row = rows["011"]
    assert "drift" in row["title"].lower()
    assert row["affected_feature"] == "transaction_amount"
    assert row["status"] == "resolved"
    assert row["source"].endswith(".md")


def test_incident_detail_returns_full_markdown():
    resp = client.get("/incidents/011")
    assert resp.status_code == 200
    body = resp.json()
    assert body["markdown"].startswith("# Incident #011")
    assert "precision" in body["markdown"].lower()
    assert client.get("/incidents/999").status_code == 404


def test_parse_incident_defaults_status_open(tmp_path):
    doc = tmp_path / "incident-777-x.md"
    doc.write_text("# Incident #777: test\n\nNo fields.\n")
    row = incidents_api.parse_incident(doc)
    assert (row["id"], row["status"]) == ("777", "open")
    assert row["affected_feature"] is None


# --- investigations list/detail ---


def test_list_investigations_newest_first_with_limit(sqlite_db):
    session = sqlite_db()
    try:
        _seed_investigation(session, query="first", hex_id="hex1")
        _seed_investigation(session, query="second", hex_id="hex2")
    finally:
        session.close()
    resp = client.get("/investigations?limit=1")
    assert resp.status_code == 200
    rows = resp.json()
    assert len(rows) == 1 and rows[0]["query"] == "second"
    assert rows[0]["investigation_id"] == "hex2"
    assert rows[0]["evidence_count"] == 1
    assert client.get("/investigations").json()[0]["query"] == "second"


def test_investigation_detail_embeds_report_and_trace(sqlite_db):
    session = sqlite_db()
    try:
        row = _seed_investigation(session)
        row_id = row.id
    finally:
        session.close()
    resp = client.get(f"/investigations/{row_id}")
    assert resp.status_code == 200
    body = resp.json()
    assert body["report"]["investigation_id"] == "hex123"
    assert len(body["trace"]) == 1 and body["trace"][0]["step"] == "reason"
    assert client.get("/investigations/9999").status_code == 404


def test_investigation_detail_handles_missing_report(sqlite_db):
    session = sqlite_db()
    try:
        row = Investigation(query="q", status="pending", report_json=None)
        session.add(row)
        session.commit()
        row_id = row.id
    finally:
        session.close()
    body = client.get(f"/investigations/{row_id}").json()
    assert body["report"] is None and body["trace"] == []
    assert body["investigation_id"] is None


# --- system summary ---


def _mock_prometheus_ok(monkeypatch):
    def fake_query(expr: str):
        if "aegis_predict_requests_total" in expr:
            return [
                {"metric": {"model_version": "v1"}, "value": [0, "1.5"]},
                {"metric": {"model_version": "v2"}, "value": [0, "4.0"]},
            ]
        if "aegis_predict_latency_seconds" in expr:
            return [{"metric": {"model_version": "v2"}, "value": [0, "0.4"]}]
        if "agent_step_duration_seconds" in expr:
            return [{"metric": {}, "value": [0, "0.02"]}]
        if "5.." in expr:
            return [{"metric": {}, "value": [0, "0.002"]}]
        return [{"metric": {}, "value": [0, "3.0"]}]

    monkeypatch.setattr(prometheus_tool, "prom_query", fake_query)


def test_system_summary_reports_values_and_count(sqlite_db, monkeypatch):
    _mock_prometheus_ok(monkeypatch)
    session = sqlite_db()
    try:
        _seed_investigation(session)
    finally:
        session.close()
    body = client.get("/system/summary").json()
    assert body["prometheus_reachable"] is True
    assert body["request_rate_per_s"] == 3.0
    assert body["error_share_5xx"] == 0.002
    assert body["predict_latency_p95_s"] == 0.4
    assert body["active_model_version"] == "v2"
    assert body["agent_avg_step_latency_s"] == 0.02
    assert body["investigations_total"] == 1


def test_system_summary_degrades_gracefully_without_prometheus(sqlite_db, monkeypatch):
    def boom(expr: str):
        raise ConnectionError("down")

    monkeypatch.setattr(prometheus_tool, "prom_query", boom)
    body = client.get("/system/summary").json()
    assert body["prometheus_reachable"] is False
    assert body["request_rate_per_s"] is None
    assert body["active_model_version"] is None
    assert body["investigations_total"] == 0
