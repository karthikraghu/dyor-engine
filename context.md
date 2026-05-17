# Trader Engine Context

## Project Snapshot

Trader Engine is a Python/FastAPI crypto strategy research engine. The current
implementation is local-first and deterministic: it can fetch Binance OHLCV
market data, store it as parquet, generate strategy decisions through a
heuristic orchestrator, execute strategy code in a sandbox, and return backtest
metrics.

Current flow:

```text
Binance OHLCV data -> parquet data store -> orchestrator strategy decision/code
-> sandbox execution -> backtest metrics
```

LLM wiring is not active yet. The AI orchestrator currently uses deterministic
market, sentiment, risk, strategy, and decision agents.

## Architecture

- `services/data_ingester`: async CCXT Binance OHLCV fetcher plus data
  validation and cleaning before writing parquet files.
- `services/sandbox`: FastAPI API for executing submitted strategy code and
  running built-in MACD/RSI backtests.
- `services/ai_orchestrator`: deterministic multi-agent decision API that
  analyzes market structure, scores headline sentiment, builds a risk plan,
  generates sandbox-compatible strategy code, and synthesizes a trading action.
- `shared/config`: environment-driven singleton config and shared logging.
- `tests`: pytest coverage for the backtester, sandbox validator/API, and AI
  orchestrator. Inspection found 35 test functions.
- `apps/frontend`: Next.js dashboard for service health, orchestrator
  decisions, generated strategy execution, built-in backtests, and result
  visualization.

The sandbox is the safety-sensitive part of the system. Preserve its defense in
depth: AST validation, restricted imports and builtins, subprocess execution,
hard timeout, Docker read-only data mount, Docker resource limits, and isolated
internal network.

## Contracts

- OHLCV data must use a UTC `DatetimeIndex` with float columns: `open`, `high`,
  `low`, `close`, `volume`.
- Strategy code submitted to `POST /execute` must define `apply_strategy(df)`.
- `apply_strategy(df)` must return a pandas DataFrame containing a `signal`
  column whose values are in `{-1, 0, 1}`.
- Sandbox code validation in `services/sandbox/code_validator.py` must run
  before any submitted strategy code is executed.
- Untrusted strategy code must keep running in a separate process with the
  configured `SANDBOX_TIMEOUT`.
- Sandbox Docker hardening in `docker-compose.yml` should not be weakened
  without explicit approval.

## Runbook

Fetch market data:

```bash
python -m services.data_ingester.fetcher --symbol "BTC/USDT" --timeframe "1h" --limit 1000
```

Run the sandbox API:

```bash
python -m uvicorn services.sandbox.app:app --host 127.0.0.1 --port 8000
```

Run the AI orchestrator API:

```bash
python -m uvicorn services.ai_orchestrator.app:app --host 127.0.0.1 --port 8010
```

Run tests:

```bash
python -m pytest tests/ -v
```

Run the frontend dashboard:

```bash
cd apps/frontend
npm install
npm run dev
```

For Docker orchestration, use:

```bash
docker-compose up -d
docker-compose down
```

## Important Caveats

- `.venv` currently appears broken in this workspace. Its `pyvenv.cfg` points to
  a Windows Store Python path that failed to launch during inspection, so
  recreate the virtual environment before relying on local test results.
- The AI orchestrator is present in tracked code in this workspace. Keep its
  status intentional if future worktree changes appear around that service.
- Some internal planning docs use legacy hyphenated paths, such as
  `services/data-ingester`. The actual repository paths use underscores, such as
  `services/data_ingester`.
- `internaldocs/` and parquet data files are intentionally ignored. Link to the
  internal docs when useful; do not duplicate their long-form roadmap content.

## What Can Be Improved

### Fix Local Development Environment First

- Recreate `.venv`; the current environment points to a non-working Windows
  Store Python executable.
- Add a root `requirements.txt` or document a single install command that
  includes all service and test dependencies.

### Keep Orchestrator Changes Intentional

- Treat `services/ai_orchestrator` as part of the current implementation.
- If future orchestrator files appear as untracked or experimental changes,
  decide whether to commit them or keep them out of version control before
  building more work on top.

### Add Missing CI

- Add `.github/workflows/ci.yml`.
- Run pytest, lint checks, and Docker build validation in CI.

### Improve Test Coverage

- Add tests for `services/data_ingester/data_validator.py`.
- Add sandbox timeout tests.
- Add edge-case tests for empty DataFrames and invalid signal values in
  `run_backtest`.
- Add orchestrator tests for bad candle payloads, missing columns, and invalid
  parquet paths.

### Tighten Sandbox Consistency

- `services/sandbox/code_validator.py` allows `json`, but the runtime restricted
  imports in `services/sandbox/app.py` only allow `pandas`, `ta`, `numpy`, and
  `math`. Align the validator and runtime import allowlists.
- Remove or reuse the unused `_make_safe_globals()` helper in
  `services/sandbox/app.py` to avoid security drift.

### Harden APIs

- Add CORS to `services/ai_orchestrator/app.py` if it will be called by the
  future frontend.
- Add rate limiting to sandbox and orchestrator endpoints.
- Consider bounding submitted code size and result DataFrame size.

## Related Docs

- High-level overview and quickstart: `README.md`
- Agent instructions and repository conventions: `AGENTS.md`
- Architecture and roadmap context: `internaldocs/MASTERPLAN.md`
- Phase 1 foundation details: `internaldocs/PHASE1_DOCUMENTATION.md`
- Phase 1.5 hardening and fixes:
  `internaldocs/PHASE_1.5_BUG_FIXES_AND_HARDENING.md`
- Bug audit context: `internaldocs/wagmi.md`
