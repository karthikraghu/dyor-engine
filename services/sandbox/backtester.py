"""
Standardized Backtester Module.

A pure-Python backtesting engine that:
  1. Reads OHLCV data from a .parquet file.
  2. Applies a trading strategy (via pandas-ta indicators).
  3. Simulates trades and computes performance metrics.
  4. Returns a JSON-serializable summary.

This module is strategy-agnostic: it can run hardcoded strategies for
validation, or execute arbitrary strategy code strings from the AI agents
(via the sandbox FastAPI layer).
"""

import json
import sys
from pathlib import Path
from dataclasses import dataclass, asdict
from typing import Optional

import numpy as np
import pandas as pd
import ta as ta_lib
from ta.trend import MACD
from ta.momentum import RSIIndicator

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from shared.config.logger import get_logger

logger = get_logger(__name__)


# ── Data Models ──────────────────────────────────────────────────────────────

@dataclass
class BacktestResult:
    strategy_name: str
    symbol: str
    timeframe: str
    start_date: str
    end_date: str
    total_candles: int
    total_trades: int
    win_rate: float
    total_return_pct: float
    sharpe_ratio: float
    max_drawdown_pct: float
    profit_factor: float
    final_equity: float
    initial_equity: float
    equity_curve: list[float]
    trades: list[dict]

    def to_json(self) -> str:
        return json.dumps(asdict(self), indent=2, default=str)

    def to_dict(self) -> dict:
        return asdict(self)


# ── Core Backtesting Engine ──────────────────────────────────────────────────

def load_data(parquet_path: str | Path) -> pd.DataFrame:
    """Load OHLCV data from a .parquet file."""
    path = Path(parquet_path)
    if not path.exists():
        raise FileNotFoundError(f"Data file not found: {path}")

    df = pd.read_parquet(path)
    logger.info(f"Loaded {len(df)} candles from {path}")
    return df


def apply_signals(df: pd.DataFrame, signal_column: str = "signal") -> pd.DataFrame:
    """
    Validate that a signal column exists with values in {1, 0, -1}.
    1 = Buy, 0 = Hold, -1 = Sell.
    """
    if signal_column not in df.columns:
        raise ValueError(f"DataFrame must contain a '{signal_column}' column.")

    df[signal_column] = df[signal_column].fillna(0).astype(int)
    return df


def run_backtest(
    df: pd.DataFrame,
    strategy_name: str = "unknown",
    symbol: str = "BTC/USDT",
    timeframe: str = "1h",
    initial_equity: float = 10_000.0,
    commission_pct: float = 0.001,  # 0.1% per trade (Binance spot)
    signal_column: str = "signal",
) -> BacktestResult:
    """
    Simulate trading based on signals and compute performance metrics.

    Expects df to have a 'signal' column:
      1  -> Enter long (buy)
      -1 -> Exit long (sell)
      0  -> Hold

    Returns:
        BacktestResult with all performance metrics.
    """
    df = apply_signals(df, signal_column)

    equity = initial_equity
    position = 0.0  # Number of units held
    entry_price = 0.0
    equity_curve = []
    trades = []

    for idx, row in df.iterrows():
        price = row["close"]
        sig = row[signal_column]

        # ── BUY signal ──
        if sig == 1 and position == 0:
            cost = equity * (1 - commission_pct)
            position = cost / price
            entry_price = price
            equity = 0.0
            trades.append({
                "type": "BUY",
                "timestamp": str(idx),
                "price": round(price, 2),
                "units": round(position, 6),
            })

        # ── SELL signal ──
        elif sig == -1 and position > 0:
            revenue = position * price * (1 - commission_pct)
            pnl_pct = ((price - entry_price) / entry_price) * 100
            trades.append({
                "type": "SELL",
                "timestamp": str(idx),
                "price": round(price, 2),
                "units": round(position, 6),
                "pnl_pct": round(pnl_pct, 2),
            })
            equity = revenue
            position = 0.0
            entry_price = 0.0

        # Track equity (mark-to-market)
        current_equity = equity + (position * price if position > 0 else 0)
        equity_curve.append(round(current_equity, 2))

    # ── If still holding at end, close position at last price ──
    if position > 0:
        last_price = df["close"].iloc[-1]
        equity = position * last_price * (1 - commission_pct)
        position = 0.0

    final_equity = equity if equity > 0 else equity_curve[-1] if equity_curve else initial_equity

    # ── Compute performance metrics ──
    equity_series = pd.Series(equity_curve)
    returns = equity_series.pct_change().dropna()

    # Sharpe Ratio (annualized, assuming hourly candles → 8760 periods/year)
    periods_per_year = _periods_per_year(timeframe)
    sharpe = 0.0
    if len(returns) > 1 and returns.std() > 0:
        sharpe = (returns.mean() / returns.std()) * np.sqrt(periods_per_year)

    # Max Drawdown
    peak = equity_series.cummax()
    drawdown = (equity_series - peak) / peak
    max_dd = abs(drawdown.min()) * 100 if len(drawdown) > 0 else 0.0

    # Win Rate
    sell_trades = [t for t in trades if t["type"] == "SELL"]
    wins = [t for t in sell_trades if t.get("pnl_pct", 0) > 0]
    win_rate = (len(wins) / len(sell_trades) * 100) if sell_trades else 0.0

    # Profit Factor
    gross_profit = sum(t["pnl_pct"] for t in sell_trades if t.get("pnl_pct", 0) > 0)
    gross_loss = abs(sum(t["pnl_pct"] for t in sell_trades if t.get("pnl_pct", 0) < 0))
    profit_factor = (gross_profit / gross_loss) if gross_loss > 0 else float("inf")

    total_return_pct = ((final_equity - initial_equity) / initial_equity) * 100

    # Subsample equity curve so JSON isn't massive (max 500 points)
    eq_out = equity_curve
    if len(equity_curve) > 500:
        step = len(equity_curve) // 500
        eq_out = equity_curve[::step]

    result = BacktestResult(
        strategy_name=strategy_name,
        symbol=symbol,
        timeframe=timeframe,
        start_date=str(df.index[0]),
        end_date=str(df.index[-1]),
        total_candles=len(df),
        total_trades=len(sell_trades),
        win_rate=round(win_rate, 2),
        total_return_pct=round(total_return_pct, 2),
        sharpe_ratio=round(sharpe, 4),
        max_drawdown_pct=round(max_dd, 2),
        profit_factor=round(profit_factor, 4) if profit_factor != float("inf") else 9999.0,
        final_equity=round(final_equity, 2),
        initial_equity=initial_equity,
        equity_curve=eq_out,
        trades=trades,
    )

    logger.info(
        f"Backtest complete: {strategy_name} | "
        f"Return: {result.total_return_pct}% | "
        f"Sharpe: {result.sharpe_ratio} | "
        f"MaxDD: {result.max_drawdown_pct}%"
    )

    return result


def _periods_per_year(timeframe: str) -> int:
    """Rough estimate of candles per year for annualization."""
    mapping = {
        "1m": 525_600,
        "5m": 105_120,
        "15m": 35_040,
        "30m": 17_520,
        "1h": 8_760,
        "4h": 2_190,
        "1d": 365,
        "1w": 52,
    }
    return mapping.get(timeframe, 8_760)


# ── Built-in Reference Strategies ────────────────────────────────────────────

def strategy_macd_crossover(df: pd.DataFrame) -> pd.DataFrame:
    """
    MACD Crossover Strategy.
    Buy when MACD crosses above the signal line.
    Sell when MACD crosses below the signal line.
    """
    macd_indicator = MACD(close=df["close"], window_slow=26, window_fast=12, window_sign=9)
    df["MACD"] = macd_indicator.macd()
    df["MACD_signal"] = macd_indicator.macd_signal()

    df["signal"] = 0
    df.loc[df["MACD"] > df["MACD_signal"], "signal"] = 1
    df.loc[df["MACD"] < df["MACD_signal"], "signal"] = -1

    # Convert to crossover signals (only trigger on transitions)
    df["signal"] = df["signal"].diff().fillna(0)
    df.loc[df["signal"] > 0, "signal"] = 1
    df.loc[df["signal"] < 0, "signal"] = -1
    df["signal"] = df["signal"].astype(int)

    return df


def strategy_rsi_mean_reversion(
    df: pd.DataFrame,
    rsi_period: int = 14,
    oversold: int = 30,
    overbought: int = 70,
) -> pd.DataFrame:
    """
    RSI Mean Reversion Strategy.
    Buy when RSI crosses below oversold threshold.
    Sell when RSI crosses above overbought threshold.
    """
    rsi_indicator = RSIIndicator(close=df["close"], window=rsi_period)
    df["RSI"] = rsi_indicator.rsi()

    df["signal"] = 0
    df.loc[df["RSI"] < oversold, "signal"] = 1
    df.loc[df["RSI"] > overbought, "signal"] = -1

    # Convert to transition signals
    df["signal"] = df["signal"].diff().fillna(0)
    df.loc[df["signal"] > 0, "signal"] = 1
    df.loc[df["signal"] < 0, "signal"] = -1
    df["signal"] = df["signal"].astype(int)

    return df


# ── CLI entry point ──────────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Run a backtest on OHLCV data")
    parser.add_argument("parquet_file", help="Path to the .parquet data file")
    parser.add_argument(
        "--strategy",
        default="macd",
        choices=["macd", "rsi"],
        help="Built-in strategy to test",
    )
    parser.add_argument("--symbol", default="BTC/USDT")
    parser.add_argument("--timeframe", default="1h")
    parser.add_argument("--equity", type=float, default=10_000.0)

    args = parser.parse_args()

    data = load_data(args.parquet_file)

    if args.strategy == "macd":
        data = strategy_macd_crossover(data)
    elif args.strategy == "rsi":
        data = strategy_rsi_mean_reversion(data)

    result = run_backtest(
        data,
        strategy_name=f"{args.strategy}_crossover",
        symbol=args.symbol,
        timeframe=args.timeframe,
        initial_equity=args.equity,
    )

    print(result.to_json())
