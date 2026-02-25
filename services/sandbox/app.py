"""
FastAPI Sandbox Service.

Provides a secure execution environment for running backtest strategy code.
The AI agents will send Python code strings to this service, which executes
them against the loaded OHLCV data and returns performance metrics.

Endpoint:
    POST /execute  — Receives a code string, runs it, returns BacktestResult JSON.
    POST /backtest — Runs a built-in strategy by name.
    GET  /health   — Health check.
"""

import sys
import traceback
from pathlib import Path
from io import StringIO
from contextlib import redirect_stdout, redirect_stderr
from typing import Optional

import pandas as pd
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
import uvicorn

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from shared.config.settings import config
from shared.config.logger import get_logger
from services.sandbox.backtester import (
    load_data,
    run_backtest,
    strategy_macd_crossover,
    strategy_rsi_mean_reversion,
    BacktestResult,
)

logger = get_logger(__name__)

app = FastAPI(
    title="Trader Engine — Execution Sandbox",
    description="Isolated execution environment for AI-generated trading strategies.",
    version="0.1.0",
)


# ── Request / Response Models ────────────────────────────────────────────────

class ExecuteRequest(BaseModel):
    code: str = Field(
        ...,
        description=(
            "Python code string that takes a DataFrame `df` with OHLCV columns "
            "(open, high, low, close, volume) and adds a 'signal' column "
            "(1=buy, -1=sell, 0=hold). The code should define a function "
            "`apply_strategy(df)` that returns the modified DataFrame."
        ),
    )
    parquet_file: Optional[str] = Field(
        default=None,
        description="Path to the .parquet file. Defaults to the configured BTC/USDT file.",
    )
    symbol: str = Field(default="BTC/USDT")
    timeframe: str = Field(default="1h")
    initial_equity: float = Field(default=10_000.0)


class BuiltinBacktestRequest(BaseModel):
    strategy: str = Field(
        ...,
        description="Name of the built-in strategy: 'macd' or 'rsi'.",
    )
    parquet_file: Optional[str] = Field(default=None)
    symbol: str = Field(default="BTC/USDT")
    timeframe: str = Field(default="1h")
    initial_equity: float = Field(default=10_000.0)


class ExecuteResponse(BaseModel):
    success: bool
    result: Optional[dict] = None
    error: Optional[str] = None
    stdout: Optional[str] = None


# ── Helper ───────────────────────────────────────────────────────────────────

def _resolve_parquet(parquet_file: Optional[str], symbol: str, timeframe: str) -> Path:
    """Resolve the parquet file path from request or config defaults."""
    if parquet_file:
        p = Path(parquet_file)
        if not p.is_absolute():
            p = config.data.data_dir / parquet_file
        return p
    return config.data.parquet_path(symbol, timeframe)


# ── Whitelisted builtins for sandboxed execution ─────────────────────────────

SAFE_BUILTINS = {
    "abs", "all", "any", "bool", "dict", "enumerate", "filter", "float",
    "frozenset", "getattr", "hasattr", "hash", "int", "isinstance",
    "issubclass", "iter", "len", "list", "map", "max", "min", "next",
    "print", "range", "repr", "reversed", "round", "set", "slice",
    "sorted", "str", "sum", "tuple", "type", "zip",
}


def _make_safe_globals(df: pd.DataFrame) -> dict:
    """
    Build a restricted globals dict for code execution.
    Allows pandas, pandas_ta, numpy, but blocks os/sys/subprocess/etc.
    """
    import numpy as np
    import ta as ta_lib

    safe_builtins = {k: __builtins__[k] if isinstance(__builtins__, dict) else getattr(__builtins__, k)
                     for k in SAFE_BUILTINS}
    # Add __import__ that only allows safe modules
    allowed_modules = {"pandas", "ta", "numpy", "math"}

    def restricted_import(name, *args, **kwargs):
        if name.split(".")[0] not in allowed_modules:
            raise ImportError(f"Import of '{name}' is not allowed in the sandbox.")
        return __import__(name, *args, **kwargs)

    safe_builtins["__import__"] = restricted_import

    return {
        "__builtins__": safe_builtins,
        "pd": pd,
        "np": np,
        "ta": ta_lib,
        "df": df.copy(),
    }


# ── Endpoints ────────────────────────────────────────────────────────────────

@app.get("/health")
async def health():
    return {"status": "ok", "service": "sandbox"}


@app.post("/execute", response_model=ExecuteResponse)
async def execute_code(request: ExecuteRequest):
    """
    Execute AI-generated strategy code against OHLCV data.

    The code must define an `apply_strategy(df)` function that:
    - Accepts a DataFrame with columns: open, high, low, close, volume
    - Adds a 'signal' column (1=buy, -1=sell, 0=hold)
    - Returns the modified DataFrame
    """
    parquet_path = _resolve_parquet(request.parquet_file, request.symbol, request.timeframe)

    try:
        df = load_data(parquet_path)
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))

    # Execute the code in a restricted environment
    stdout_capture = StringIO()
    stderr_capture = StringIO()

    try:
        safe_globals = _make_safe_globals(df)

        with redirect_stdout(stdout_capture), redirect_stderr(stderr_capture):
            exec(request.code, safe_globals)

            # The code must define `apply_strategy`
            if "apply_strategy" not in safe_globals:
                return ExecuteResponse(
                    success=False,
                    error="Code must define an `apply_strategy(df)` function.",
                    stdout=stdout_capture.getvalue(),
                )

            result_df = safe_globals["apply_strategy"](safe_globals["df"])

        if not isinstance(result_df, pd.DataFrame):
            return ExecuteResponse(
                success=False,
                error="apply_strategy() must return a pandas DataFrame.",
                stdout=stdout_capture.getvalue(),
            )

        if "signal" not in result_df.columns:
            return ExecuteResponse(
                success=False,
                error="Returned DataFrame must contain a 'signal' column.",
                stdout=stdout_capture.getvalue(),
            )

        # Run the backtest
        backtest_result = run_backtest(
            result_df,
            strategy_name="ai_generated",
            symbol=request.symbol,
            timeframe=request.timeframe,
            initial_equity=request.initial_equity,
        )

        return ExecuteResponse(
            success=True,
            result=backtest_result.to_dict(),
            stdout=stdout_capture.getvalue(),
        )

    except Exception as e:
        tb = traceback.format_exc()
        logger.error(f"Code execution failed: {e}\n{tb}")
        return ExecuteResponse(
            success=False,
            error=f"{type(e).__name__}: {str(e)}",
            stdout=stdout_capture.getvalue(),
        )


@app.post("/backtest", response_model=ExecuteResponse)
async def run_builtin_backtest(request: BuiltinBacktestRequest):
    """Run a built-in strategy backtest."""
    parquet_path = _resolve_parquet(request.parquet_file, request.symbol, request.timeframe)

    try:
        df = load_data(parquet_path)
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))

    strategies = {
        "macd": ("macd_crossover", strategy_macd_crossover),
        "rsi": ("rsi_mean_reversion", strategy_rsi_mean_reversion),
    }

    if request.strategy not in strategies:
        return ExecuteResponse(
            success=False,
            error=f"Unknown strategy '{request.strategy}'. Available: {list(strategies.keys())}",
        )

    name, strategy_fn = strategies[request.strategy]

    try:
        df = strategy_fn(df)
        result = run_backtest(
            df,
            strategy_name=name,
            symbol=request.symbol,
            timeframe=request.timeframe,
            initial_equity=request.initial_equity,
        )
        return ExecuteResponse(success=True, result=result.to_dict())

    except Exception as e:
        tb = traceback.format_exc()
        logger.error(f"Backtest failed: {e}\n{tb}")
        return ExecuteResponse(
            success=False,
            error=f"{type(e).__name__}: {str(e)}",
        )


# ── Entry Point ──────────────────────────────────────────────────────────────

if __name__ == "__main__":
    uvicorn.run(
        "services.sandbox.app:app",
        host=config.sandbox.host,
        port=config.sandbox.port,
        reload=True,
    )
