.PHONY: dev backend frontend migrate test lint install install-api

BACKEND_DIR := backend
FRONTEND_DIR := frontend

install:
	cd $(BACKEND_DIR) && pip install -e ".[dev,pipeline]"
	cd $(FRONTEND_DIR) && npm install

install-api:
	cd $(BACKEND_DIR) && pip install .

backend:
	cd $(BACKEND_DIR) && uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

frontend:
	cd $(FRONTEND_DIR) && npm run dev

dev:
	@echo "Run 'make backend' and 'make frontend' in separate terminals."

migrate:
	cd $(BACKEND_DIR) && alembic upgrade head

migrate-down:
	cd $(BACKEND_DIR) && alembic downgrade -1

ingest:
	cd $(BACKEND_DIR) && ingest ingest --months 6

analyze:
	cd $(BACKEND_DIR) && analyze analyze --dry-run

test:
	cd $(BACKEND_DIR) && pytest -m "not integration"
	cd $(FRONTEND_DIR) && npm run test

lint:
	cd $(BACKEND_DIR) && ruff check . && mypy core app db ingestion pipeline
	cd $(FRONTEND_DIR) && npm run lint
