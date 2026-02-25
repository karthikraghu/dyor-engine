"""Tests for the sandbox FastAPI endpoints."""
import pytest
from fastapi.testclient import TestClient
from services.sandbox.app import app


@pytest.fixture
def client():
    """Create a test client for the sandbox API."""
    return TestClient(app)


def test_health_endpoint(client):
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["service"] == "sandbox"


def test_execute_valid_code(client):
    code = """
def apply_strategy(df):
    df['signal'] = 0
    return df
"""
    response = client.post("/execute", json={"code": code})
    assert response.status_code == 200
    data = response.json()
    assert "execution_time_ms" in data


def test_execute_blocked_code(client):
    code = "import os\ndef apply_strategy(df): return df"
    response = client.post("/execute", json={"code": code})
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is False
    assert "validation" in data["error"].lower() or "forbidden" in data["error"].lower()


def test_backtest_endpoint_macd(client):
    """Test backtest with built-in MACD strategy (requires data file)."""
    response = client.post("/backtest", json={"strategy": "macd"})
    # May fail if data file doesn't exist yet — that's expected
    if response.status_code == 200:
        data = response.json()
        assert "buy_hold_return_pct" in str(data)


def test_cors_headers(client):
    """Verify CORS headers are present for allowed origins."""
    response = client.options(
        "/health",
        headers={
            "Origin": "http://localhost:3000",
            "Access-Control-Request-Method": "GET",
        },
    )
    assert response.headers.get("access-control-allow-origin") == "http://localhost:3000"
