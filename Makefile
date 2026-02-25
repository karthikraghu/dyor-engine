.PHONY: help up down test fetch lint format sandbox clean

help:  ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-15s\033[0m %s\n", $$1, $$2}'

up:  ## Start all services (docker-compose up)
	docker-compose up -d

down:  ## Stop all services
	docker-compose down

test:  ## Run pytest test suite
	python -m pytest tests/ -v

fetch:  ## Fetch latest OHLCV data
	python -m services.data_ingester.fetcher

sandbox:  ## Start sandbox server locally (dev mode)
	python -m services.sandbox.app

lint:  ## Run ruff linter
	python -m ruff check . --fix

format:  ## Run ruff formatter
	python -m ruff format .

clean:  ## Remove cached files
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -name "*.pyc" -delete 2>/dev/null || true
