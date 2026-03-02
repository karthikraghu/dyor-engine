"""
Asynchronous OHLCV data fetcher using ccxt.

Fetches historical candlestick data from Binance (no API key needed for
public market data) and persists it as .parquet files for fast downstream
consumption by the backtester and AI agents.
"""

import asyncio
import sys
from pathlib import Path
from datetime import datetime, timezone
from typing import Optional

import ccxt.async_support as ccxt_async
import aiohttp
import pandas as pd

# Allow imports from project root
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from shared.config.settings import config
from shared.config.logger import get_logger
from services.data_ingester.data_validator import validate_and_clean

logger = get_logger(__name__)


async def fetch_ohlcv(
    symbol: str | None = None,
    timeframe: str | None = None,
    limit: int | None = None,
    since: Optional[int] = None,
) -> pd.DataFrame:
    """
    Fetch OHLCV data from Binance and return as a DataFrame.

    Args:
        symbol: Trading pair, e.g. 'BTC/USDT'. Defaults to config value.
        timeframe: Candle timeframe, e.g. '1h', '15m', '1d'. Defaults to config value.
        limit: Max number of candles to fetch per request. Defaults to config value.
        since: Start timestamp in milliseconds. If None, fetches the latest candles.

    Returns:
        DataFrame with columns: timestamp, open, high, low, close, volume
    """
    symbol = symbol or config.exchange.trading_pair
    timeframe = timeframe or config.exchange.timeframe
    limit = limit or config.exchange.ohlcv_limit

    exchange = ccxt_async.binance({
        "enableRateLimit": True,
        "connector_params": {
            "resolver": aiohttp.ThreadedResolver()
        }
    })

    try:
        logger.info(f"Fetching {limit} candles of {symbol} ({timeframe}) from Binance...")

        ohlcv = await exchange.fetch_ohlcv(
            symbol=symbol,
            timeframe=timeframe,
            limit=limit,
            since=since,
        )

        logger.info(f"Received {len(ohlcv)} candles.")

        df = pd.DataFrame(
            ohlcv,
            columns=["timestamp", "open", "high", "low", "close", "volume"],
        )

        # Convert timestamp from ms to datetime
        df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms", utc=True)
        df = df.set_index("timestamp")

        # Ensure correct dtypes
        for col in ["open", "high", "low", "close", "volume"]:
            df[col] = df[col].astype(float)

        # Validate data quality
        df, report = validate_and_clean(df, timeframe=timeframe)
        if not report.is_clean:
            logger.warning(f"Data quality issues: {report}")

        return df

    finally:
        await exchange.close()


async def fetch_and_save(
    symbol: str | None = None,
    timeframe: str | None = None,
    limit: int | None = None,
    since: Optional[int] = None,
) -> Path:
    """
    Fetch OHLCV data and save to a Parquet file.

    Returns:
        Path to the saved .parquet file.
    """
    symbol = symbol or config.exchange.trading_pair
    timeframe = timeframe or config.exchange.timeframe

    df = await fetch_ohlcv(symbol, timeframe, limit, since)

    # Ensure data directory exists
    config.data.data_dir.mkdir(parents=True, exist_ok=True)
    out_path = config.data.parquet_path(symbol, timeframe)

    # If file already exists, merge and deduplicate
    if out_path.exists():
        existing = pd.read_parquet(out_path)
        df = pd.concat([existing, df])
        df = df[~df.index.duplicated(keep="last")]
        df = df.sort_index()
        logger.info(f"Merged with existing data. Total candles: {len(df)}")

    df.to_parquet(out_path, engine="pyarrow")
    logger.info(f"Saved {len(df)} candles to {out_path}")

    return out_path


async def fetch_full_history(
    symbol: str | None = None,
    timeframe: str | None = None,
    since_date: str = "2024-01-01",
    batch_size: int = 1000,
) -> Path:
    """
    Fetch extended historical data by paginating through time.

    Args:
        symbol: Trading pair.
        timeframe: Candle timeframe.
        since_date: ISO date string to start from (e.g. '2024-01-01').
        batch_size: Number of candles per request.

    Returns:
        Path to the saved .parquet file.
    """
    symbol = symbol or config.exchange.trading_pair
    timeframe = timeframe or config.exchange.timeframe

    exchange = ccxt_async.binance({
        "enableRateLimit": True,
        "connector_params": {
            "resolver": aiohttp.ThreadedResolver()
        }
    })
    since_ms = int(
        datetime.strptime(since_date, "%Y-%m-%d")
        .replace(tzinfo=timezone.utc)
        .timestamp()
        * 1000
    )

    all_candles = []

    try:
        logger.info(
            f"Fetching full history of {symbol} ({timeframe}) since {since_date}..."
        )

        while True:
            ohlcv = await exchange.fetch_ohlcv(
                symbol=symbol,
                timeframe=timeframe,
                since=since_ms,
                limit=batch_size,
            )

            if not ohlcv:
                break

            all_candles.extend(ohlcv)
            since_ms = ohlcv[-1][0] + 1  # Move past the last candle

            logger.info(
                f"  Fetched {len(ohlcv)} candles, total so far: {len(all_candles)}"
            )

            if len(ohlcv) < batch_size:
                break  # No more data available

            await asyncio.sleep(0.1)  # Be polite to the API

    finally:
        await exchange.close()

    df = pd.DataFrame(
        all_candles,
        columns=["timestamp", "open", "high", "low", "close", "volume"],
    )
    df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms", utc=True)
    df = df.set_index("timestamp")
    df = df[~df.index.duplicated(keep="last")]
    df = df.sort_index()

    for col in ["open", "high", "low", "close", "volume"]:
        df[col] = df[col].astype(float)

    # Validate data quality
    df, report = validate_and_clean(df, timeframe=timeframe)
    if not report.is_clean:
        logger.warning(f"Data quality issues in full history: {report}")

    config.data.data_dir.mkdir(parents=True, exist_ok=True)
    out_path = config.data.parquet_path(symbol, timeframe)
    df.to_parquet(out_path, engine="pyarrow")

    logger.info(f"Saved {len(df)} candles to {out_path}")
    return out_path


# ── CLI entry point ──────────────────────────────────────────────────────────
if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="CCXT OHLCV Data Fetcher")
    parser.add_argument("--symbol", default=None, help="Trading pair (e.g. BTC/USDT)")
    parser.add_argument("--timeframe", default=None, help="Candle timeframe (e.g. 1h)")
    parser.add_argument("--limit", type=int, default=None, help="Number of candles")
    parser.add_argument(
        "--full-history",
        action="store_true",
        help="Fetch extended history from --since date",
    )
    parser.add_argument(
        "--since",
        default="2024-01-01",
        help="Start date for full history (YYYY-MM-DD)",
    )

    args = parser.parse_args()

    if args.full_history:
        asyncio.run(
            fetch_full_history(
                symbol=args.symbol,
                timeframe=args.timeframe,
                since_date=args.since,
            )
        )
    else:
        asyncio.run(
            fetch_and_save(
                symbol=args.symbol,
                timeframe=args.timeframe,
                limit=args.limit,
            )
        )
