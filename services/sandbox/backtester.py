"""
Standardized Backtester Module.

A pure-Python backtesting engine that:
  1. Reads OHLCV data from a .parquet file.
  2. Applies a trading strategy (via ta library indicators).
  3. Simulates trades and computes performance metrics.
  4. Returns a JSON-serializable summary.

This module is strategy-agnostic: it can run hardcoded strategies for
validation, or execute arbitrary strategy code strings from the AI agents
(via the sandbox FastAPI layer).

Metrics computed:
  - Total Return % + Buy-and-Hold benchmark comparison
  - Sharpe Ratio (annualized)
  - Sortino Ratio (downside-only volatility)
  - Calmar Ratio (annual return / max drawdown)
  - Max Drawdown %
  - Win Rate %
  - Profit Factor (dollar-based, not percentage-based)
  - Slippage model (configurable, default 0.05%)
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


# ── Metrics Descriptions (for AI analysis) ───────────────────────────────────

METRICS_FOR_AI_ANALYSIS = {
    "total_return_pct": "Total return percentage of the strategy over the backtest period.",
    "buy_hold_return_pct": "Buy-and-hold benchmark return percentage for comparison.",
    "sharpe_ratio": "Annualized Sharpe Ratio — risk-adjusted return (reward per unit of total volatility).",
    "sortino_ratio": "Annualized Sortino Ratio — risk-adjusted return penalizing only downside volatility.",
    "calmar_ratio": "Calmar Ratio — annualized return divided by maximum drawdown.",
    "max_drawdown_pct": "Maximum drawdown percentage — largest peak-to-trough equity decline.",
    "win_rate": "Win rate percentage — fraction of trades that were profitable.",
    "profit_factor": "Profit Factor — gross profit divided by gross loss (dollar-based).",
    "total_trades": "Total number of completed (round-trip) trades.",
    "final_equity": "Final portfolio equity after all trades.",
    "initial_equity": "Starting portfolio equity.",
    "total_candles": "Total number of OHLCV candles in the backtest period.",
}


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
    buy_hold_return_pct: float
    sharpe_ratio: float
    sortino_ratio: float
    calmar_ratio: float
    max_drawdown_pct: float
    profit_factor: float
    final_equity: float
    initial_equity: float
    slippage_pct: float
    commission_pct: float
    equity_curve: list[float]
    trades: list[dict]

    def to_json(self) -> str:
        return json.dumps(asdict(self), indent=2, default=str)

    def to_dict(self) -> dict:
        return asdict(self)

    def metrics_for_ai(self) -> dict:
        """
        Return a summary of performance metrics intended for AI analysis.

        Excludes raw data (equity_curve, trades) and configuration fields,
        returning only the key performance metrics with descriptions that
        help the AI understand what each value represents.
        """
        metrics = {
            key: {
                "value": getattr(self, key),
                "description": METRICS_FOR_AI_ANALYSIS[key],
            }
            for key in METRICS_FOR_AI_ANALYSIS
        }
        metrics["strategy_name"] = {"value": self.strategy_name, "description": "Name of the strategy evaluated."}
        metrics["symbol"] = {"value": self.symbol, "description": "Trading pair symbol."}
        metrics["timeframe"] = {"value": self.timeframe, "description": "Candle timeframe used."}
        metrics["start_date"] = {"value": self.start_date, "description": "Backtest start date."}
        metrics["end_date"] = {"value": self.end_date, "description": "Backtest end date."}
        return metrics


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
    slippage_pct: float = 0.0005,   # 0.05% slippage per fill
    signal_column: str = "signal",
) -> BacktestResult:
    """
    Simulate trading based on signals and compute performance metrics.

    Expects df to have a 'signal' column:
      1  -> Enter long (buy)
      -1 -> Exit long (sell)
      0  -> Hold

    Features:
      - Slippage model (fills are worse than close price)
      - Dollar-based profit factor
      - Buy-and-hold benchmark
      - Sortino & Calmar ratios
      - Equity curve matches final_equity on force-close

    Returns:
        BacktestResult with all performance metrics.
    """
    df = apply_signals(df, signal_column)
    signals = df[signal_column].values
    closes = df["close"].values
    n = len(df)

    equity = initial_equity
    position = 0.0
    entry_price = 0.0
    equity_curve = np.empty(n, dtype=np.float64)
    trades = []

    for i in range(n):
        price = closes[i]
        sig = signals[i]

        # ── BUY signal ──
        if sig == 1 and position == 0:
            fill_price = price * (1 + slippage_pct)  # Slippage: buy higher
            cost = equity * (1 - commission_pct)
            position = cost / fill_price
            entry_price = fill_price
            equity = 0.0
            trades.append({
                "type": "BUY",
                "timestamp": str(df.index[i]),
                "price": round(fill_price, 2),
                "units": round(position, 8),
            })

        # ── SELL signal ──
        elif sig == -1 and position > 0:
            fill_price = price * (1 - slippage_pct)  # Slippage: sell lower
            revenue = position * fill_price * (1 - commission_pct)
            pnl_dollar = revenue - (position * entry_price)
            pnl_pct = ((fill_price - entry_price) / entry_price) * 100
            trades.append({
                "type": "SELL",
                "timestamp": str(df.index[i]),
                "price": round(fill_price, 2),
                "units": round(position, 8),
                "pnl_pct": round(pnl_pct, 2),
                "pnl_dollar": round(pnl_dollar, 2),
            })
            equity = revenue
            position = 0.0
            entry_price = 0.0

        # Mark-to-market equity
        equity_curve[i] = equity + (position * closes[i] if position > 0 else 0)

    # ── Force-close open position at end (BUG 6 fix) ──
    if position > 0:
        last_price = closes[-1] * (1 - slippage_pct)
        revenue = position * last_price * (1 - commission_pct)
        pnl_dollar = revenue - (position * entry_price)
        pnl_pct = ((last_price - entry_price) / entry_price) * 100
        trades.append({
            "type": "SELL",
            "timestamp": str(df.index[-1]),
            "price": round(last_price, 2),
            "units": round(position, 8),
            "pnl_pct": round(pnl_pct, 2),
            "pnl_dollar": round(pnl_dollar, 2),
            "forced_close": True,
        })
        equity = revenue
        position = 0.0
        equity_curve[-1] = equity  # Equity curve matches final_equity

    final_equity = equity if equity > 0 else equity_curve[-1] if n > 0 else initial_equity

    # ── Performance Metrics ──
    eq_series = pd.Series(equity_curve)
    returns = eq_series.pct_change().dropna()
    periods_per_year = _periods_per_year(timeframe)

    # Sharpe Ratio (annualized)
    sharpe = 0.0
    if len(returns) > 1 and returns.std() > 0:
        sharpe = (returns.mean() / returns.std()) * np.sqrt(periods_per_year)

    # Sortino Ratio (only penalizes downside volatility)
    sortino = 0.0
    downside = returns[returns < 0]
    if len(downside) > 1 and downside.std() > 0:
        sortino = (returns.mean() / downside.std()) * np.sqrt(periods_per_year)

    # Max Drawdown
    peak = eq_series.cummax()
    drawdown = (eq_series - peak) / peak
    max_dd = abs(drawdown.min()) * 100 if len(drawdown) > 0 else 0.0

    # Win Rate
    sell_trades = [t for t in trades if t["type"] == "SELL"]
    wins = [t for t in sell_trades if t.get("pnl_dollar", 0) > 0]
    win_rate = (len(wins) / len(sell_trades) * 100) if sell_trades else 0.0

    # Profit Factor — DOLLAR-BASED (BUG 7 fix)
    gross_profit = sum(t["pnl_dollar"] for t in sell_trades if t.get("pnl_dollar", 0) > 0)
    gross_loss = abs(sum(t["pnl_dollar"] for t in sell_trades if t.get("pnl_dollar", 0) < 0))
    profit_factor = (gross_profit / gross_loss) if gross_loss > 0 else float("inf")

    total_return_pct = ((final_equity - initial_equity) / initial_equity) * 100

    # Buy-and-Hold Benchmark
    bnh_units = (initial_equity * (1 - commission_pct)) / (closes[0] * (1 + slippage_pct))
    bnh_final = bnh_units * closes[-1] * (1 - slippage_pct) * (1 - commission_pct)
    bnh_return_pct = ((bnh_final - initial_equity) / initial_equity) * 100

    # Calmar Ratio (annualized return / max drawdown)
    calmar = 0.0
    annual_return = total_return_pct * (periods_per_year / n) if n > 0 else 0.0
    if max_dd > 0:
        calmar = annual_return / max_dd

    # Subsample equity curve (max 500 points for JSON)
    eq_list = equity_curve.tolist()
    eq_out = eq_list
    if len(eq_list) > 500:
        step = len(eq_list) // 500
        eq_out = eq_list[::step]

    result = BacktestResult(
        strategy_name=strategy_name,
        symbol=symbol,
        timeframe=timeframe,
        start_date=str(df.index[0]),
        end_date=str(df.index[-1]),
        total_candles=n,
        total_trades=len(sell_trades),
        win_rate=round(win_rate, 2),
        total_return_pct=round(total_return_pct, 2),
        buy_hold_return_pct=round(bnh_return_pct, 2),
        sharpe_ratio=round(sharpe, 4),
        sortino_ratio=round(sortino, 4),
        calmar_ratio=round(calmar, 4),
        max_drawdown_pct=round(max_dd, 2),
        profit_factor=round(profit_factor, 4) if profit_factor != float("inf") else 9999.0,
        final_equity=round(final_equity, 2),
        initial_equity=initial_equity,
        slippage_pct=slippage_pct,
        commission_pct=commission_pct,
        equity_curve=eq_out,
        trades=trades,
    )

    logger.info(
        f"Backtest complete: {strategy_name} | "
        f"Return: {result.total_return_pct}% | "
        f"B&H: {result.buy_hold_return_pct}% | "
        f"Sharpe: {result.sharpe_ratio} | "
        f"Sortino: {result.sortino_ratio} | "
        f"MaxDD: {result.max_drawdown_pct}%"
    )

    # Log all metrics retrieved for AI analysis
    ai_metrics = result.metrics_for_ai()
    metric_names = list(ai_metrics)
    logger.info(
        f"Metrics retrieved for AI analysis: {', '.join(metric_names)}"
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
