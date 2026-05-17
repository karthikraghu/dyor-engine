# DYOR Engine

An AI-powered crypto trading strategy generator. It analyzes market data, generates trading strategies using LLM agents, backtests them in an isolated sandbox, and displays results on a dashboard.

## How It Works

```
Binance ──► Data Fetcher ──► Market Data (.parquet)
                                    │
                                    ▼
                            AI Agents (heuristic now, LLM-ready)
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
├── data_ingester/     # Fetches OHLCV data from Binance via CCXT
├── sandbox/           # Backtesting engine + FastAPI execution API
└── ai_orchestrator/   # Multi-agent trading decision orchestrator API

apps/
└── frontend/          # Next.js dashboard for decisions and backtests
```

## Quick Start

```bash
# 1. Install dependencies
pip install ccxt pandas pyarrow python-dotenv ta fastapi uvicorn numpy

# 2. Set up config
cp .env.example .env

# 3. Fetch market data
python -m services.data_ingester.fetcher --symbol "BTC/USDT" --timeframe "1h" --limit 1000

# 4. Run a backtest
python -m services.sandbox.backtester data/BTC_USDT_1h.parquet --strategy macd

# 5. Start the sandbox API
python -m uvicorn services.sandbox.app:app --host 127.0.0.1 --port 8000

# 6. Start the AI orchestrator API
python -m uvicorn services.ai_orchestrator.app:app --host 127.0.0.1 --port 8010

# 7. Start the frontend dashboard
cd apps/frontend
npm install
npm run dev
```

Open the dashboard at `http://localhost:3000`. By default it calls the sandbox
API at `http://localhost:8000` and the orchestrator API at
`http://localhost:8010`. Override those with `NEXT_PUBLIC_SANDBOX_API_URL` and
`NEXT_PUBLIC_ORCHESTRATOR_API_URL` in `apps/frontend/.env.local` if needed.

## Tech Stack

- **Python** — Core language for data + AI
- **CCXT** — Exchange connectivity (Binance)
- **FastAPI** — Sandbox execution API
- **Deterministic multi-agent pipeline (LLM-ready)** — Trading decision orchestration
- **Docker** — Service containerization
- **Next.js + shadcn/ui** — Frontend dashboard

## License

MIT
