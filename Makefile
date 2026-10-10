# Comandos locales. Requiere: Python 3.12, Node 20+, PostgreSQL 16/17 local y apps/api/.env.
API=apps/api
WEB=apps/web
ENV=set -a && . ./.env && set +a

.PHONY: setup api-setup web-setup db-up migrate seed admin api web test api-test web-test

setup: api-setup web-setup

api-setup:
	cd $(API) && python3.12 -m venv .venv && .venv/bin/pip install -r requirements-dev.txt

web-setup:
	cd $(WEB) && npm ci

db-up:
	docker compose up -d db

migrate:
	cd $(API) && $(ENV) && .venv/bin/alembic upgrade head

seed:
	cd $(API) && $(ENV) && .venv/bin/python -m exam_engine.cli seed-catalog seeds/udl_siaf_catalog.json

# make admin            → crea/restablece 'admin' (pide contraseña)
# make admin TEMP=1     → contraseña temporal: obliga a cambiarla al entrar
admin:
	cd $(API) && $(ENV) && .venv/bin/python -m exam_engine.cli create-admin --username admin \
		--display-name "Administrador" --role platform_admin $(if $(TEMP),--temporary,)

api:
	cd $(API) && $(ENV) && .venv/bin/uvicorn exam_engine.main:app --reload --port 8000

web:
	cd $(WEB) && npm run dev

api-test:
	cd $(API) && $(ENV) && .venv/bin/ruff check . && .venv/bin/ruff format --check . && .venv/bin/python -m pytest -q

web-test:
	cd $(WEB) && npm run lint && npm run typecheck && npm test && npm run build && npm run check:bundle

test: api-test web-test
