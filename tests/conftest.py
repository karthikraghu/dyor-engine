import pytest
import pandas as pd
import numpy as np


@pytest.fixture
def sample_ohlcv():
    """Create a synthetic OHLCV DataFrame with known values."""
    np.random.seed(42)
    n = 100
    dates = pd.date_range("2025-01-01", periods=n, freq="1h", tz="UTC")
    close = 50000 + np.cumsum(np.random.randn(n) * 100)
    df = pd.DataFrame(
        {
            "open": close - np.random.rand(n) * 50,
            "high": close + np.random.rand(n) * 100,
            "low": close - np.random.rand(n) * 100,
            "close": close,
            "volume": np.random.rand(n) * 1000,
        },
        index=dates,
    )
    return df


@pytest.fixture
def sample_ohlcv_with_signals(sample_ohlcv):
    """OHLCV with alternating buy/sell signals."""
    df = sample_ohlcv.copy()
    df["signal"] = 0
    df.iloc[10, df.columns.get_loc("signal")] = 1  # Buy
    df.iloc[20, df.columns.get_loc("signal")] = -1  # Sell
    df.iloc[40, df.columns.get_loc("signal")] = 1  # Buy
    df.iloc[60, df.columns.get_loc("signal")] = -1  # Sell
    return df
