"""
FastAPI service for the AI trading orchestrator.

Exposes a deterministic multi-agent decision endpoint that can operate on either:
1. A parquet file on disk, or
2. Inline candle payloads from callers.
"""

from __future__ import annotations

from datetime import datetime
import sys
from pathlib import Path
from typing import Literal, Optional

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
import pandas as pd
import uvicorn

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from shared.config.logger import get_logger
from shared.config.settings import config
from services.ai_orchestrator.orchestrator import TradingOrchestrator


logger = get_logger(__name__)
orchestrator = TradingOrchestrator()
_valid_risk_profiles = {"conservative", "balanced", "aggressive"}
if config.orchestrator.default_risk_profile not in _valid_risk_profiles:
    raise ValueError(
        "Invalid ORCHESTRATOR_RISK_PROFILE value. "
        "Expected one of: ['aggressive', 'balanced', 'conservative']."
    )

app = FastAPI(
    title="Trader Engine - AI Orchestrator",
    description="Multi-agent orchestration service for trading decisions and strategy generation.",
    version="0.1.0",
)


class Candle(BaseModel):
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float


class DecisionRequest(BaseModel):
    symbol: str = Field(default="BTC/USDT")
    timeframe: str = Field(default="1h")
    risk_profile: Literal["conservative", "balanced", "aggressive"] = Field(
        default=config.orchestrator.default_risk_profile
    )
    headlines: list[str] = Field(default_factory=list)
    parquet_file: Optional[str] = Field(
        default=None,
        description="Optional parquet path. Relative paths resolve from DATA_DIR.",
    )
    candles: Optional[list[Candle]] = Field(
        default=None,
        description="Inline OHLCV candles. If provided, parquet_file is ignored.",
    )


@app.get("/health")
async def health() -> dict:
    return {
        "status": "ok",
        "service": "ai_orchestrator",
        "model_provider": config.orchestrator.model_provider,
        "model_name": config.orchestrator.model_name,
    }


@app.post("/decision")
async def build_decision(request: DecisionRequest) -> dict:
    try:
        df = _load_request_dataframe(request)
        result = orchestrator.orchestrate(
            df=df,
            symbol=request.symbol,
            timeframe=request.timeframe,
            risk_profile=request.risk_profile,
            headlines=request.headlines,
        )
        return {"success": True, "result": result.to_dict()}
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("Failed to orchestrate trading decision: %s", exc)
        raise HTTPException(
            status_code=500,
            detail="Internal error while generating decision.",
        ) from exc


def _load_request_dataframe(request: DecisionRequest) -> pd.DataFrame:
    if request.candles:
        return _candles_to_df(request.candles)

    parquet_path = _resolve_parquet_path(
        parquet_file=request.parquet_file,
        symbol=request.symbol,
        timeframe=request.timeframe,
    )
    if not parquet_path.exists():
        raise FileNotFoundError(f"Data file not found: {parquet_path}")
    return pd.read_parquet(parquet_path)


def _resolve_parquet_path(parquet_file: Optional[str], symbol: str, timeframe: str) -> Path:
    if parquet_file:
        path = Path(parquet_file)
        if not path.is_absolute():
            path = config.data.data_dir / parquet_file
        return path

    return config.data.parquet_path(symbol, timeframe)


def _candles_to_df(candles: list[Candle]) -> pd.DataFrame:
    records = [
        {
            "timestamp": candle.timestamp,
            "open": candle.open,
            "high": candle.high,
            "low": candle.low,
            "close": candle.close,
            "volume": candle.volume,
        }
        for candle in candles
    ]
    df = pd.DataFrame.from_records(records)
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
    return df.set_index("timestamp").sort_index()


if __name__ == "__main__":
    uvicorn.run(
        "services.ai_orchestrator.app:app",
        host=config.orchestrator.host,
        port=config.orchestrator.port,
        reload=True,
    )
