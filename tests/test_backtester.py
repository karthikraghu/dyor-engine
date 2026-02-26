"""Tests for the backtesting engine."""
from services.sandbox.backtester import run_backtest, BacktestResult, METRICS_FOR_AI_ANALYSIS


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


def test_metrics_for_ai_contains_all_expected_keys(sample_ohlcv_with_signals):
    result = run_backtest(sample_ohlcv_with_signals)
    ai_metrics = result.metrics_for_ai()
    for key in METRICS_FOR_AI_ANALYSIS:
        assert key in ai_metrics
        assert "value" in ai_metrics[key]
        assert "description" in ai_metrics[key]


def test_metrics_for_ai_includes_context_fields(sample_ohlcv_with_signals):
    result = run_backtest(sample_ohlcv_with_signals)
    ai_metrics = result.metrics_for_ai()
    for field in ("strategy_name", "symbol", "timeframe", "start_date", "end_date"):
        assert field in ai_metrics
        assert "value" in ai_metrics[field]
        assert "description" in ai_metrics[field]


def test_metrics_for_ai_excludes_raw_data(sample_ohlcv_with_signals):
    result = run_backtest(sample_ohlcv_with_signals)
    ai_metrics = result.metrics_for_ai()
    assert "equity_curve" not in ai_metrics
    assert "trades" not in ai_metrics


def test_metrics_for_ai_values_match_result(sample_ohlcv_with_signals):
    result = run_backtest(sample_ohlcv_with_signals)
    ai_metrics = result.metrics_for_ai()
    assert ai_metrics["total_return_pct"]["value"] == result.total_return_pct
    assert ai_metrics["sharpe_ratio"]["value"] == result.sharpe_ratio
    assert ai_metrics["win_rate"]["value"] == result.win_rate
    assert ai_metrics["total_trades"]["value"] == result.total_trades
