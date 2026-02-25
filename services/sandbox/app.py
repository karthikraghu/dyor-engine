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
import time
import traceback
import multiprocessing
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
from services.sandbox.code_validator import validate_code

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
    execution_time_ms: Optional[int] = None


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


# ── Subprocess Code Execution with Timeout ──────────────────────────────────

def _exec_worker(code: str, df_bytes: bytes, result_queue: multiprocessing.Queue):
    """
    Worker function that runs in a separate process.
    Executes code, applies strategy, runs backtest, and puts the result in the queue.
    """
    import io
    import traceback
    import pandas as pd
    import numpy as np
    import ta as ta_lib
    from services.sandbox.backtester import run_backtest

    stdout_capture = StringIO()
    stderr_capture = StringIO()

    try:
        df = pd.read_parquet(io.BytesIO(df_bytes))

        safe_builtins = {k: __builtins__[k] if isinstance(__builtins__, dict) else getattr(__builtins__, k)
                         for k in SAFE_BUILTINS}
        allowed_modules = {"pandas", "ta", "numpy", "math"}

        def restricted_import(name, *args, **kwargs):
            if name.split(".")[0] not in allowed_modules:
                raise ImportError(f"Import of '{name}' is not allowed in the sandbox.")
            return __import__(name, *args, **kwargs)

        safe_builtins["__import__"] = restricted_import

        safe_globals = {
            "__builtins__": safe_builtins,
            "pd": pd,
            "np": np,
            "ta": ta_lib,
            "df": df.copy(),
        }

        with io.StringIO() as stdout_buf, io.StringIO() as stderr_buf:
            import contextlib
            with contextlib.redirect_stdout(stdout_buf), contextlib.redirect_stderr(stderr_buf):
                exec(code, safe_globals)

                if "apply_strategy" not in safe_globals:
                    result_queue.put({
                        "success": False,
                        "error": "Code must define an `apply_strategy(df)` function.",
                        "stdout": stdout_buf.getvalue(),
                    })
                    return

                result_df = safe_globals["apply_strategy"](safe_globals["df"])

            stdout_text = stdout_buf.getvalue()

        if not isinstance(result_df, pd.DataFrame):
            result_queue.put({"success": False, "error": "apply_strategy() must return a pandas DataFrame.", "stdout": stdout_text})
            return

        if "signal" not in result_df.columns:
            result_queue.put({"success": False, "error": "Returned DataFrame must contain a 'signal' column.", "stdout": stdout_text})
            return

        result_queue.put({"success": True, "result_df_bytes": result_df.to_parquet(), "stdout": stdout_text})

    except Exception as e:
        result_queue.put({
            "success": False,
            "error": f"{type(e).__name__}: {str(e)}",
            "stdout": "",
        })


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
    start_time = time.perf_counter()
    parquet_path = _resolve_parquet(request.parquet_file, request.symbol, request.timeframe)

    # AST validation BEFORE execution (BUG 5 fix)
    validation = validate_code(request.code)
    if not validation.is_safe:
        elapsed_ms = int((time.perf_counter() - start_time) * 1000)
        return ExecuteResponse(
            success=False,
            error=f"Code validation failed: {'; '.join(validation.violations)}",
            execution_time_ms=elapsed_ms,
        )

    try:
        df = load_data(parquet_path)
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))

    # Serialize DataFrame for subprocess transfer
    import io as _io
    df_bytes = df.to_parquet()

    # Execute code in a subprocess with timeout
    result_queue = multiprocessing.Queue()
    process = multiprocessing.Process(
        target=_exec_worker,
        args=(request.code, df_bytes, result_queue),
    )
    process.start()
    process.join(timeout=config.sandbox.timeout)

    elapsed_ms = int((time.perf_counter() - start_time) * 1000)

    if process.is_alive():
        process.kill()
        process.join(timeout=5)
        logger.warning(f"Code execution timed out after {config.sandbox.timeout}s")
        return ExecuteResponse(
            success=False,
            error=f"Execution timed out after {config.sandbox.timeout} seconds.",
            execution_time_ms=elapsed_ms,
        )

    try:
        worker_result = result_queue.get_nowait()
    except Exception:
        return ExecuteResponse(
            success=False,
            error="Code execution failed: worker process exited without result.",
            execution_time_ms=elapsed_ms,
        )

    if not worker_result["success"]:
        return ExecuteResponse(
            success=False,
            error=worker_result.get("error", "Unknown error"),
            stdout=worker_result.get("stdout"),
            execution_time_ms=elapsed_ms,
        )

    # Worker succeeded — deserialize result_df and run backtest in main process
    try:
        result_df = pd.read_parquet(_io.BytesIO(worker_result["result_df_bytes"]))

        backtest_result = run_backtest(
            result_df,
            strategy_name="ai_generated",
            symbol=request.symbol,
            timeframe=request.timeframe,
            initial_equity=request.initial_equity,
        )

        elapsed_ms = int((time.perf_counter() - start_time) * 1000)
        return ExecuteResponse(
            success=True,
            result=backtest_result.to_dict(),
            stdout=worker_result.get("stdout"),
            execution_time_ms=elapsed_ms,
        )

    except Exception as e:
        tb = traceback.format_exc()
        logger.error(f"Backtest after execution failed: {e}\n{tb}")
        elapsed_ms = int((time.perf_counter() - start_time) * 1000)
        return ExecuteResponse(
            success=False,
            error=f"{type(e).__name__}: {str(e)}",
            stdout=worker_result.get("stdout"),
            execution_time_ms=elapsed_ms,
        )


@app.post("/backtest", response_model=ExecuteResponse)
async def run_builtin_backtest(request: BuiltinBacktestRequest):
    """Run a built-in strategy backtest."""
    start_time = time.perf_counter()
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
            execution_time_ms=int((time.perf_counter() - start_time) * 1000),
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
        elapsed_ms = int((time.perf_counter() - start_time) * 1000)
        return ExecuteResponse(success=True, result=result.to_dict(), execution_time_ms=elapsed_ms)

    except Exception as e:
        tb = traceback.format_exc()
        logger.error(f"Backtest failed: {e}\n{tb}")
        elapsed_ms = int((time.perf_counter() - start_time) * 1000)
        return ExecuteResponse(
            success=False,
            error=f"{type(e).__name__}: {str(e)}",
            execution_time_ms=elapsed_ms,
        )


# ── Entry Point ──────────────────────────────────────────────────────────────

if __name__ == "__main__":
    uvicorn.run(
        "services.sandbox.app:app",
        host=config.sandbox.host,
        port=config.sandbox.port,
        reload=True,
    )
