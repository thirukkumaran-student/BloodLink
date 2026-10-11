# BloodLink developer commands (OWNER: D1, spec §27 "validation commands").
#
# Everything a feature developer needs, in the order they need it.

PYTHONPATH := apps/api:packages/config:packages/contracts:packages/validation
PY := PYTHONPATH=$(PYTHONPATH) python3

# Ports are overridable so a second app built from the same specification can run
# side by side: `make api API_PORT=8010` + `make web WEB_PORT=5174 API_PORT=8010`.
API_PORT ?= 8000
WEB_PORT ?= 5173
API_URL ?= http://127.0.0.1:$(API_PORT)

# PostgreSQL: used by `make api-postgres` / `make test-postgres`.
# The test database must be disposable — the suite drops every table in it.
DATABASE_URL ?= postgresql+psycopg://bloodlink:bloodlink@localhost:5432/bloodlink
TEST_DATABASE_URL ?= postgresql+psycopg://bloodlink:bloodlink@localhost:5432/bloodlink_test

.PHONY: help install api web dev test test-contracts test-privacy docs export-contracts \
        migrate migrate-new seed build check clean reset-db smoke smoke-web \
        install-postgres setup-postgres api-postgres test-postgres

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-18s\033[0m %s\n", $$1, $$2}'

install: ## Install Python and Node dependencies
	pip3 install -r requirements.txt
	npm install

install-postgres: ## Install the PostgreSQL driver (everything in requirements.txt plus psycopg)
	pip3 install -r requirements-postgres.txt

setup-postgres: ## PostgreSQL: create the databases, migrate, write .env, print next steps (re-runnable)
	@./scripts/setup_postgres.sh $(if $(filter command line environment,$(origin DATABASE_URL)),"$(DATABASE_URL)",)

api: ## Run the API (http://localhost:$(API_PORT), docs at /docs) — override with API_PORT=…
	$(PY) -m uvicorn bloodlink_api.main:app --reload --host 0.0.0.0 --port $(API_PORT)

api-postgres: ## Run the API against PostgreSQL (uses .env unless DATABASE_URL=… is given)
	$(if $(filter command line environment,$(origin DATABASE_URL)),BLOODLINK_DATABASE_URL="$(DATABASE_URL)" ,)$(PY) -m uvicorn bloodlink_api.main:app --reload --host 0.0.0.0 --port $(API_PORT)

test-postgres: ## Run the full test suite against PostgreSQL (override TEST_DATABASE_URL=…)
	BLOODLINK_TEST_DATABASE_URL="$(TEST_DATABASE_URL)" $(PY) -m pytest -q

web: ## Run the web client (http://localhost:$(WEB_PORT), proxies /api -> $(API_URL))
	BLOODLINK_WEB_PORT=$(WEB_PORT) BLOODLINK_API_URL=$(API_URL) npm run dev

dev: ## Reminder: run `make api` and `make web` in two terminals
	@echo "Terminal 1: make api    Terminal 2: make web"

test: ## Run the full Python test suite (contracts, privacy, RBAC, acceptance, architecture)
	$(PY) -m pytest -q

test-contracts: ## Contract + ownership + lifecycle tests only
	$(PY) -m pytest -q tests/test_contracts.py tests/test_web_contract_parity.py

test-privacy: ## Privacy guarantees only
	$(PY) -m pytest -q tests/test_privacy.py

smoke: ## End-to-end smoke of the seeded demo (API must be running)
	$(PY) scripts/smoke_flow.py

smoke-web: ## Browser-shaped smoke: Vite proxy + the SPA booted in a DOM (API + dev server running)
	$(PY) scripts/smoke_web_flow.py
	node scripts/web_boot_smoke.mjs

build: ## Build the web client (Vite, plain JS/JSX)
	npm run build

export-contracts: ## Regenerate docs/ownership.md, docs/api-contracts.md, docs/rbac.md
	$(PY) scripts/export_contracts.py

docs: export-contracts ## Alias for export-contracts

migrate: ## Apply migrations (D1 owns the single history)
	$(PY) -m alembic upgrade head

migrate-new: ## Create a revision (D1 only): make migrate-new m="add table"
	$(PY) -m alembic revision --autogenerate -m "$(m)"

seed: ## Seed the demo dataset
	$(PY) -m bloodlink_api.seed

check: test build export-contracts ## Everything CI runs

reset-db: ## Delete the local SQLite database (stop the API first!)
	@echo "Stop the running API before resetting: deleting the SQLite file under a live server leaves it writing to an unlinked inode."
	rm -f bloodlink.db
	@echo "Database removed — restart the API to create and seed a fresh one."

clean: ## Remove build artefacts and caches
	rm -rf apps/web/dist apps/web/node_modules packages/ui/node_modules node_modules/.vite .pytest_cache
	find . -name "__pycache__" -type d -prune -exec rm -rf {} +
