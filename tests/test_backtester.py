"""Tests for the backtesting engine."""
from services.sandbox.backtester import run_backtest, BacktestResult


def test_backtest_returns_result(sample_ohlcv_with_signals):
    result = run_backtest(sample_ohlcv_with_signals, initial_equity=10000)
    assert isinstance(result, BacktestResult)
    assert result.total_trades == 2
    assert result.initial_equity == 10000


def test_backtest_equity_curve_length(sample_ohlcv_with_signals):
    result = run_backtest(sample_ohlcv_with_signals)
    assert len(result.equity_curve) <= 500


def test_backtest_buy_and_hold(sample_ohlcv_with_signals):
    result = run_backtest(sample_ohlcv_with_signals)
    assert result.buy_hold_return_pct is not None


def test_backtest_final_equity_matches_curve(sample_ohlcv_with_signals):
    result = run_backtest(sample_ohlcv_with_signals)
    assert abs(result.equity_curve[-1] - result.final_equity) < 1.0


def test_backtest_slippage_reduces_returns(sample_ohlcv_with_signals):
    r1 = run_backtest(sample_ohlcv_with_signals, slippage_pct=0.0)
    r2 = run_backtest(sample_ohlcv_with_signals, slippage_pct=0.01)
    # Higher slippage should result in lower returns
    assert r2.total_return_pct <= r1.total_return_pct


def test_backtest_no_signals_no_trades(sample_ohlcv):
    sample_ohlcv["signal"] = 0
    result = run_backtest(sample_ohlcv)
    assert result.total_trades == 0
    assert result.final_equity == 10000.0


def test_backtest_profit_factor_is_dollar_based(sample_ohlcv_with_signals):
    result = run_backtest(sample_ohlcv_with_signals)
    for t in result.trades:
        if t["type"] == "SELL":
            assert "pnl_dollar" in t


def test_backtest_sortino_ratio_computed(sample_ohlcv_with_signals):
    result = run_backtest(sample_ohlcv_with_signals)
    assert result.sortino_ratio is not None


def test_backtest_calmar_ratio_computed(sample_ohlcv_with_signals):
    result = run_backtest(sample_ohlcv_with_signals)
    assert result.calmar_ratio is not None


def test_backtest_to_json(sample_ohlcv_with_signals):
    result = run_backtest(sample_ohlcv_with_signals)
    json_str = result.to_json()
    assert "strategy_name" in json_str
    assert "buy_hold_return_pct" in json_str


def test_backtest_to_dict(sample_ohlcv_with_signals):
    result = run_backtest(sample_ohlcv_with_signals)
    d = result.to_dict()
    assert isinstance(d, dict)
    assert "trades" in d
