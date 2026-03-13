.PHONY: help dev-up dev-down bootstrap test lint format clean

PYTHON := python3
PIP    := pip3

help:  ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
	  awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-22s\033[0m %s\n", $$1, $$2}'

# ── Infrastructure ──────────────────────────────────────────────────────────

dev-up:  ## Start all local infrastructure (DB, Kafka, Redis, MLflow, MinIO)
	docker compose up -d
	@echo "⏳  Waiting for TimescaleDB to be ready..."
	@until docker compose exec timescaledb pg_isready -U scada -d scada_db 2>/dev/null; do sleep 1; done
	@echo "✅  Infrastructure ready"

dev-down:  ## Stop all local infrastructure
	docker compose down

dev-reset:  ## Stop + wipe all volumes (DESTRUCTIVE)
	docker compose down -v --remove-orphans

logs:  ## Tail all service logs
	docker compose logs -f

# ── Database ────────────────────────────────────────────────────────────────

migrate:  ## Run Alembic migrations
	cd apps/api && alembic upgrade head

migrate-down:  ## Rollback last Alembic migration
	cd apps/api && alembic downgrade -1

migrate-gen:  ## Auto-generate a new migration (msg="your message")
	cd apps/api && alembic revision --autogenerate -m "$(msg)"

# ── Data & Bootstrap ────────────────────────────────────────────────────────

bootstrap:  ## Full local setup: migrate + load sample data
	$(MAKE) migrate
	$(PYTHON) scripts/ingest_sample.py
	@echo "🌱  Sample data loaded"

download-kelmarsh:  ## Download real Kelmarsh dataset from Zenodo
	$(PYTHON) scripts/download_kelmarsh.py

download-sample:  ## Download small sample only (fast)
	$(PYTHON) scripts/download_kelmarsh.py --sample

# ── Python Packages ─────────────────────────────────────────────────────────

install:  ## Install all Python packages in editable mode
	$(PIP) install -e packages/shared -e packages/analytics -e packages/connectors
	$(PIP) install -r apps/api/requirements.txt
	$(PIP) install -r apps/ingestion/requirements.txt

install-dev:  ## Install dev extras (pytest, ruff, mypy)
	$(MAKE) install
	$(PIP) install pytest pytest-asyncio pytest-cov ruff mypy httpx

# ── Frontend ────────────────────────────────────────────────────────────────

frontend-install:  ## Install Node dependencies
	cd apps/frontend && npm install

frontend-dev:  ## Start Vite dev server
	cd apps/frontend && npm run dev

frontend-build:  ## Build production bundle
	cd apps/frontend && npm run build

# ── API ─────────────────────────────────────────────────────────────────────

api-dev:  ## Start FastAPI dev server with hot-reload
	cd apps/api && uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# ── Quality ─────────────────────────────────────────────────────────────────

test:  ## Run full test suite
	pytest tests/ -v --cov=packages --cov-report=term-missing

test-unit:  ## Run unit tests only
	pytest tests/ -v -m "not integration"

lint:  ## Lint Python code with ruff
	ruff check packages/ apps/api/ apps/ingestion/ tests/

format:  ## Format Python code with ruff
	ruff format packages/ apps/api/ apps/ingestion/ tests/

typecheck:  ## Type-check with mypy
	mypy packages/ apps/api/

# ── Utility ─────────────────────────────────────────────────────────────────

clean:  ## Remove build artefacts and caches
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name "*.egg-info" -exec rm -rf {} + 2>/dev/null || true
	find . -name "*.pyc" -delete
	rm -rf .pytest_cache htmlcov .coverage coverage.xml
	@echo "🧹  Clean"
