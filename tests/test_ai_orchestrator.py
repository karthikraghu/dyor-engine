"""Tests for the AI orchestrator service and decision pipeline."""

from fastapi.testclient import TestClient

from services.ai_orchestrator.app import app
from services.ai_orchestrator.orchestrator import TradingOrchestrator


def test_orchestrator_returns_structured_decision(sample_ohlcv):
    orchestrator = TradingOrchestrator()
    result = orchestrator.orchestrate(
        df=sample_ohlcv,
        symbol="BTC/USDT",
        timeframe="1h",
        risk_profile="balanced",
        headlines=["Bitcoin adoption surges after strong ETF inflows"],
    )

    payload = result.to_dict()
    assert payload["decision"]["action"] in {"enter_long", "reduce_risk", "wait", "hold_cash"}
    assert "apply_strategy" in payload["strategy"]["code"]
    assert payload["risk"]["position_size_pct"] > 0


def test_orchestrator_defaults_to_neutral_sentiment(sample_ohlcv):
    orchestrator = TradingOrchestrator()
    result = orchestrator.orchestrate(
        df=sample_ohlcv,
        symbol="BTC/USDT",
        timeframe="1h",
        risk_profile="conservative",
        headlines=[],
    )
    assert result.sentiment.bias == "neutral"
    assert result.sentiment.headlines_analyzed == 0


def test_ai_orchestrator_health_endpoint():
    client = TestClient(app)
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["service"] == "ai_orchestrator"


def test_ai_orchestrator_cors_headers():
    client = TestClient(app)
    response = client.options(
        "/decision",
        headers={
            "Origin": "http://localhost:3000",
            "Access-Control-Request-Method": "POST",
        },
    )
    assert response.headers.get("access-control-allow-origin") == "http://localhost:3000"


def test_decision_endpoint_with_inline_candles(sample_ohlcv):
    client = TestClient(app)

    sample = sample_ohlcv.head(80).reset_index()
    candles = [
        {
            "timestamp": row["index"].isoformat(),
            "open": float(row["open"]),
            "high": float(row["high"]),
            "low": float(row["low"]),
            "close": float(row["close"]),
            "volume": float(row["volume"]),
        }
        for _, row in sample.iterrows()
    ]

    response = client.post(
        "/decision",
        json={
            "symbol": "BTC/USDT",
            "timeframe": "1h",
            "risk_profile": "balanced",
            "headlines": ["Markets rebound as institutional demand strengthens"],
            "candles": candles,
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True
    assert "decision" in payload["result"]
    assert "strategy" in payload["result"]
