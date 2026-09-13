"""Backend tests for the Phase 2 model-serving routes."""
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)

FRAUD_TXN = {
    "transaction_amount": 900.0,
    "merchant_category": "electronics",
    "hour_of_day": 3,
}
LEGIT_TXN = {
    "transaction_amount": 12.5,
    "merchant_category": "grocery",
    "hour_of_day": 13,
}


def test_models_lists_all_three_versions_with_metrics():
    resp = client.get("/models")
    assert resp.status_code == 200
    models = {m["model_version"]: m for m in resp.json()["models"]}
    assert {"v1", "v2", "v3"} <= set(models)
    for version in ("v1", "v2", "v3"):
        entry = models[version]
        assert entry["artifact_present"] is True
        metrics = entry["metrics"]
        assert metrics is not None
        for key in ("accuracy", "precision", "recall", "model_version",
                    "timestamp", "dataset_version"):
            assert key in metrics, f"{version} metrics missing {key}"
        assert metrics["model_version"] == version


def test_model_metrics_show_expected_degradations():
    """Acceptance encoded: v2 precision drops (FP rise), v3 recall drops."""
    resp = client.get("/models")
    models = {m["model_version"]: m["metrics"] for m in resp.json()["models"]}
    assert models["v2"]["precision"] < models["v1"]["precision"] - 0.05
    assert models["v2"]["false_positives"] > models["v1"]["false_positives"]
    assert models["v3"]["recall"] < models["v1"]["recall"] - 0.10


def test_predict_returns_scored_response_for_every_version():
    for version in ("v1", "v2", "v3"):
        resp = client.post("/predict", json={**FRAUD_TXN, "model_version": version})
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["model_version"] == version
        assert isinstance(body["is_fraud"], bool)
        assert 0.0 <= body["fraud_probability"] <= 1.0


def test_predict_ranks_obvious_fraud_above_obvious_legit():
    fraud = client.post("/predict", json=FRAUD_TXN).json()
    legit = client.post("/predict", json=LEGIT_TXN).json()
    assert fraud["fraud_probability"] > legit["fraud_probability"]
    assert fraud["is_fraud"] is True
    assert legit["is_fraud"] is False


def test_predict_defaults_to_v1():
    resp = client.post("/predict", json=dict(LEGIT_TXN))
    assert resp.status_code == 200
    assert resp.json()["model_version"] == "v1"


def test_predict_unknown_version_returns_404():
    resp = client.post("/predict", json={**LEGIT_TXN, "model_version": "v99"})
    assert resp.status_code == 404


def test_predict_invalid_input_returns_422():
    assert client.post("/predict", json={**LEGIT_TXN, "hour_of_day": 99}).status_code == 422
    assert client.post("/predict", json={**LEGIT_TXN, "transaction_amount": -5}).status_code == 422
