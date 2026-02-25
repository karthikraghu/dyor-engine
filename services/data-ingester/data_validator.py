"""
Data quality validation for OHLCV DataFrames.
Checks for gaps, nulls, duplicates, and anomalies.
"""
import pandas as pd
from dataclasses import dataclass, field

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from shared.config.logger import get_logger

logger = get_logger(__name__)

TIMEFRAME_TO_FREQ = {
    "1m": "1min", "5m": "5min", "15m": "15min", "30m": "30min",
    "1h": "1h", "4h": "4h", "1d": "1D", "1w": "1W",
}


@dataclass
class ValidationReport:
    total_rows: int = 0
    duplicates_removed: int = 0
    null_rows_found: int = 0
    null_rows_filled: int = 0
    gaps_found: int = 0
    gaps_filled: int = 0
    anomalies: list[str] = field(default_factory=list)
    is_clean: bool = True


def validate_and_clean(
    df: pd.DataFrame,
    timeframe: str = "1h",
    fill_gaps: bool = True,
    max_gap_fill: int = 3,  # Only fill gaps up to 3 missing candles
) -> tuple[pd.DataFrame, ValidationReport]:
    """
    Validate OHLCV DataFrame and optionally clean issues.

    Checks performed:
      1. Duplicate timestamp removal
      2. Null value detection and forward-fill
      3. Timestamp gap detection and optional fill
      4. Anomaly detection (high < low, zero/negative prices)

    Args:
        df: OHLCV DataFrame with DatetimeIndex.
        timeframe: Candle timeframe string (e.g. '1h', '15m').
        fill_gaps: Whether to forward-fill small gaps.
        max_gap_fill: Maximum consecutive missing candles to fill.

    Returns:
        Tuple of (cleaned DataFrame, ValidationReport)
    """
    report = ValidationReport(total_rows=len(df))

    # 1. Remove duplicates
    before = len(df)
    df = df[~df.index.duplicated(keep="last")]
    report.duplicates_removed = before - len(df)
    if report.duplicates_removed > 0:
        logger.warning(f"Removed {report.duplicates_removed} duplicate timestamps")
        report.is_clean = False

    # 2. Check for null values
    null_mask = df[["open", "high", "low", "close", "volume"]].isnull().any(axis=1)
    report.null_rows_found = int(null_mask.sum())
    if report.null_rows_found > 0:
        logger.warning(f"Found {report.null_rows_found} rows with null values")
        report.is_clean = False
        # Forward-fill nulls (price doesn't change = flat candle)
        df[["open", "high", "low", "close"]] = df[["open", "high", "low", "close"]].ffill()
        df["volume"] = df["volume"].fillna(0)
        report.null_rows_filled = report.null_rows_found

    # 3. Check for timestamp gaps
    df = df.sort_index()
    freq = TIMEFRAME_TO_FREQ.get(timeframe, "1h")
    expected_index = pd.date_range(start=df.index[0], end=df.index[-1], freq=freq)
    missing = expected_index.difference(df.index)
    report.gaps_found = len(missing)

    if report.gaps_found > 0:
        logger.warning(f"Found {report.gaps_found} missing candles in expected timeline")
        report.is_clean = False

        if fill_gaps and report.gaps_found <= max_gap_fill * 10:  # Don't fill huge gaps
            df = df.reindex(expected_index)
            df[["open", "high", "low", "close"]] = df[["open", "high", "low", "close"]].ffill()
            df["volume"] = df["volume"].fillna(0)
            report.gaps_filled = report.gaps_found
            logger.info(f"Forward-filled {report.gaps_filled} missing candles")

    # 4. Anomaly detection: candles where high < low (exchange error)
    bad_candles = df[df["high"] < df["low"]]
    if len(bad_candles) > 0:
        report.anomalies.append(f"{len(bad_candles)} candles where high < low")
        report.is_clean = False

    # 5. Anomaly detection: zero-price candles
    zero_price = df[(df["close"] <= 0) | (df["open"] <= 0)]
    if len(zero_price) > 0:
        report.anomalies.append(f"{len(zero_price)} candles with zero/negative price")
        report.is_clean = False

    report.total_rows = len(df)
    return df, report
