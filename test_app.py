"""
Unit tests for the Moby Dick FastAPI book recommendation service.

Run with:
    pytest test_app.py -v
"""

import numpy as np
import pytest
from unittest.mock import MagicMock, patch
from fastapi.testclient import TestClient

import app as app_module
from app import app


@pytest.fixture(autouse=True)
def reset_model():
    app_module.model = None
    yield
    app_module.model = None


@pytest.fixture
def client():
    return TestClient(app)


# GET /
class TestRootEndpoint:
    def test_returns_200(self, client):
        response = client.get("/")
        assert response.status_code == 200

    def test_returns_expected_message(self, client):
        response = client.get("/")
        assert response.json() == {"message": "This is our model for recommending books"}

    def test_content_type_is_json(self, client):
        response = client.get("/")
        assert "application/json" in response.headers["content-type"]


# GET /health
class TestHealthEndpoint:
    def test_model_not_loaded_returns_not_up(self, client):
        response = client.get("/health")
        assert response.status_code == 200
        assert response.json() == "Model is not up"

    def test_model_loaded_returns_up(self, client):
        app_module.model = MagicMock()
        response = client.get("/health")
        assert response.status_code == 200
        assert response.json() == "Model exists and is up"


# POST /predict
class TestPredictEndpoint:
    def test_predict_returns_200(self, client):
        app_module.model = MagicMock()
        app_module.model.predict.return_value = np.array(["Book A", "Book B"])
        response = client.post("/predict", json={"book_query": "adventure on the sea"})
        assert response.status_code == 200

    def test_predict_returns_query_and_predictions(self, client):
        app_module.model = MagicMock()
        app_module.model.predict.return_value = np.array(["Book A", "Book B"])
        response = client.post("/predict", json={"book_query": "adventure on the sea"})
        body = response.json()
        assert body["book_query"] == "adventure on the sea"
        assert body["predictions"] == ["Book A", "Book B"]

    def test_predict_rejects_query_too_short(self, client):
        app_module.model = MagicMock()
        response = client.post("/predict", json={"book_query": "ab"})
        assert response.status_code == 422

    def test_predict_rejects_missing_query(self, client):
        app_module.model = MagicMock()
        response = client.post("/predict", json={})
        assert response.status_code == 422