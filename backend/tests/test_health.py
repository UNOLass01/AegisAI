"""Backend tests: health endpoint + investigations table definition."""
from fastapi.testclient import TestClient

from app.main import app
from app.models import Investigation

client = TestClient(app)


def test_health_returns_ok():
    resp = client.get("/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["service"] == "aegis-ai"


def test_root_returns_service_info():
    resp = client.get("/")
    assert resp.status_code == 200
    assert resp.json()["service"] == "aegis-ai"


def test_investigation_model_has_required_columns():
    cols = {c.name for c in Investigation.__table__.columns}
    assert {"id", "created_at", "query", "status", "root_cause", "confidence", "report_json"} <= cols
    assert Investigation.__tablename__ == "investigations"
