# DYOR Engine

An AI-powered crypto trading strategy generator. It analyzes market data, generates trading strategies using LLM agents, backtests them in an isolated sandbox, and displays results on a dashboard.

## How It Works

```
Binance ──► Data Fetcher ──► Market Data (.parquet)
                                    │
                                    ▼
                            AI Agents (Gemini Pro)
                            ├── Analyze market context
                            ├── Score news sentiment
                            └── Generate strategy code
                                    │
                                    ▼
                            Execution Sandbox
                            ├── Run strategy safely
                            ├── Simulate trades
                            └── Calculate performance
                                    │
                                    ▼
                            Dashboard (Next.js)
                            └── View results & equity curves
```

## Project Structure

```
services/
├── data-ingester/     # Fetches OHLCV data from Binance via CCXT
├── sandbox/           # Backtesting engine + FastAPI execution API
└── ai-orchestrator/   # LangGraph multi-agent system (coming soon)

apps/
└── frontend/          # Next.js dashboard (coming soon)
```

## Quick Start

```bash
# 1. Install dependencies
pip install ccxt pandas pyarrow python-dotenv ta fastapi uvicorn numpy

# 2. Set up config
cp .env.example .env

# 3. Fetch market data
python -m services.data-ingester.fetcher --symbol "BTC/USDT" --timeframe "1h" --limit 1000

# 4. Run a backtest
python -m services.sandbox.backtester data/BTC_USDT_1h.parquet --strategy macd

# 5. Start the sandbox API
python -m uvicorn services.sandbox.app:app --host 127.0.0.1 --port 8000
```

## Tech Stack

- **Python** — Core language for data + AI
- **CCXT** — Exchange connectivity (Binance)
- **FastAPI** — Sandbox execution API
- **LangGraph + Gemini Pro** — Multi-agent orchestration
- **Docker** — Service containerization
- **Next.js** — Frontend dashboard

## License

MIT
