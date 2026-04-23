# Trader Engine Agent Instructions

This file helps coding agents become productive quickly in this repository.
Keep changes minimal, validate behavior with tests, and preserve sandbox safety defaults.

## First Steps

1. If needed, copy `.env.example` to `.env` and adjust values.
2. Use the active virtual environment before running Python commands.
3. Use direct commands from [README.md](README.md):
  - `python -m pytest tests/ -v`
  - `python -m services.data_ingester.fetcher`
  - `python -m services.sandbox.app`
  - `python -m ruff check . --fix`
  - `python -m ruff format .`
4. For Docker orchestration, use `docker-compose up -d` and `docker-compose down`.

## Project Layout And Boundaries

- `services/data_ingester`: Fetches and validates OHLCV data, writes parquet files.
- `services/sandbox`: FastAPI sandbox, code validation, and backtesting engine.
- `services/ai_orchestrator`: Planned for Phase 2, currently scaffolded.
- `shared/config`: Central configuration and logging utilities.
- `tests`: Pytest suite for sandbox API, validator, and backtester.
- `apps/frontend`: Planned dashboard app.

## Non-Obvious Conventions

- Configuration access uses a singleton:
  - `from shared.config.settings import config`
- Logging uses:
  - `from shared.config.logger import get_logger`
  - `logger = get_logger(__name__)`
- Service modules commonly add repo root to `sys.path` for `shared` imports.
- OHLCV DataFrame contract is a UTC `DatetimeIndex` with float columns:
  `open`, `high`, `low`, `close`, `volume`.
- Strategy code contract for `/execute`:
  - Must define `apply_strategy(df)`.
  - Must return a DataFrame with `signal` in `{-1, 0, 1}`.

## Critical Safety Invariants

- Do not bypass or remove AST validation in `services/sandbox/code_validator.py`.
- Untrusted code must keep running in a separate process with timeout (`SANDBOX_TIMEOUT`).
- Do not weaken sandbox hardening in `docker-compose.yml` without explicit approval:
  - read-only data mount for sandbox (`./data:/app/data:ro`)
  - isolated internal network for sandbox (`sandbox-net`)
  - CPU and memory limits on sandbox container

## Testing Expectations

- Primary test command: `python -m pytest tests/ -v`.
- When changing sandbox execution or validation, run:
  - `tests/test_sandbox_api.py`
  - `tests/test_code_validator.py`
- When changing backtesting logic, run:
  - `tests/test_backtester.py`
- Keep existing behavioral guarantees, including:
  - final equity aligns with last equity curve value
  - profit factor remains dollar-based

## Documentation To Link, Not Duplicate

- High-level overview and quickstart: [README.md](README.md)
- Roadmap and architecture planning: [internaldocs/theplan.md](internaldocs/theplan.md)
- Master phased execution plan: [internaldocs/MASTERPLAN.md](internaldocs/MASTERPLAN.md)
- Phase 1 foundation details: [internaldocs/PHASE1_DOCUMENTATION.md](internaldocs/PHASE1_DOCUMENTATION.md)
- Phase 1.5 hardening and fixes: [internaldocs/PHASE_1.5_BUG_FIXES_AND_HARDENING.md](internaldocs/PHASE_1.5_BUG_FIXES_AND_HARDENING.md)
- Bug audit context: [internaldocs/wagmi.md](internaldocs/wagmi.md)

## Known Pitfall

Some planning docs use legacy directory names with hyphens (for example `data-ingester`).
Current code uses underscores (for example `services/data_ingester`). Prefer actual repository paths.
