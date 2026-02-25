"""
Centralized configuration for the Trader Engine.
Reads from environment variables / .env file.
"""

import os
from pathlib import Path
from dataclasses import dataclass, field
from dotenv import load_dotenv

# Load .env from project root
_project_root = Path(__file__).resolve().parents[2]
load_dotenv(_project_root / ".env")


@dataclass(frozen=True)
class ExchangeConfig:
    exchange_id: str = os.getenv("EXCHANGE_ID", "binance")
    trading_pair: str = os.getenv("TRADING_PAIR", "BTC/USDT")
    timeframe: str = os.getenv("TIMEFRAME", "1h")
    ohlcv_limit: int = int(os.getenv("OHLCV_LIMIT", "1000"))


@dataclass(frozen=True)
class DataConfig:
    data_dir: Path = field(
        default_factory=lambda: Path(os.getenv("DATA_DIR", str(_project_root / "data")))
    )

    def parquet_path(self, symbol: str, timeframe: str) -> Path:
        """Return the path for a parquet file given symbol and timeframe."""
        safe_symbol = symbol.replace("/", "_")
        return self.data_dir / f"{safe_symbol}_{timeframe}.parquet"


@dataclass(frozen=True)
class SandboxConfig:
    host: str = os.getenv("SANDBOX_HOST", "0.0.0.0")
    port: int = int(os.getenv("SANDBOX_PORT", "8000"))


@dataclass(frozen=True)
class AppConfig:
    exchange: ExchangeConfig = field(default_factory=ExchangeConfig)
    data: DataConfig = field(default_factory=DataConfig)
    sandbox: SandboxConfig = field(default_factory=SandboxConfig)


# Singleton config instance
config = AppConfig()
