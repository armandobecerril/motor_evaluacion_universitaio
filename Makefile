# Comandos locales. Requiere: Python 3.12, Node 20+, PostgreSQL 16/17 local.
API=apps/api
WEB=apps/web
PY=$(API)/.venv/bin/python

.PHONY: setup api-setup web-setup db-up migrate seed test api-test web-test lint build check

setup: api-setup web-setup

api-setup:
	cd $(API) && python3.12 -m venv .venv && .venv/bin/pip install -r requirements-dev.txt

web-setup:
	cd $(WEB) && npm ci

db-up:
	docker compose up -d db

migrate:
	cd $(API) && set -a && . ./.env && set +a && .venv/bin/alembic upgrade head

seed:
	cd $(API) && set -a && . ./.env && set +a && .venv/bin/python -m scripts.seed_catalog seeds/siaf_catalog.json

api-test:
	cd $(API) && set -a && . ./.env && set +a && .venv/bin/ruff check . && .venv/bin/ruff format --check . && .venv/bin/python -m pytest -q

web-test:
	cd $(WEB) && npm run lint && npm run typecheck && npm test && npm run build && npm run check:bundle

test: api-test web-test
