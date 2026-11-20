PY := api/.venv/bin/python
PIP := api/.venv/bin/pip
PYTEST := api/.venv/bin/pytest
ALEMBIC := api/.venv/bin/alembic

.PHONY: up down api-dev web-dev migrate seed test test-e2e eval api-openapi lint fmt install

up:
	docker compose up -d postgres

down:
	docker compose down

install:
	python3.11 -m venv api/.venv
	$(PIP) install -q -r api/requirements.txt
	cd web && npm install

api-dev:
	cd api && .venv/bin/uvicorn app.main:app --reload --port 8000

web-dev:
	cd web && npm run dev

migrate:
	cd api && .venv/bin/alembic upgrade head

seed:
	cd api && .venv/bin/python -m seed

test:
	cd api && .venv/bin/pytest -q

test-e2e:
	cd web && npx playwright test

eval:
	PYTHONPATH=api api/.venv/bin/python eval/run_eval.py --prompt-versions v1_basic,v2_criterion_anchored

api-openapi:
	cd api && .venv/bin/python -c "import json; from app.main import app; print(json.dumps(app.openapi(), indent=2))" > ../openapi.json

lint:
	api/.venv/bin/ruff check api
	api/.venv/bin/mypy api/app api/scripts api/seed.py

fmt:
	api/.venv/bin/ruff format api
	api/.venv/bin/ruff check --fix api
