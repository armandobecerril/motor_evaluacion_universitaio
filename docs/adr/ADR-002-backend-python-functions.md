# ADR-002 — Backend en Python: FastAPI en Azure App Service

- **Estado:** aceptado (2026-10-10). Sustituye la versión del 2026-10-09 (Azure Functions Python), que a su vez reemplazó a Functions TypeScript.

## Decisión
API en **FastAPI (Python 3.12)** sobre **Azure App Service Linux (plan B1)**, servida con `gunicorn -k uvicorn.workers.UvicornWorker`. Frontend React + Vite + TypeScript en Azure Static Web Apps (Standard) con la App Service como backend vinculado.

## Motivo
- ADR-001 exige SQLAlchemy 2 + Alembic (Python).
- Un examen de 20 s por pregunta no tolera arranques en frío; App Service mantiene el proceso activo.
- Pool de conexiones estable: 1 instancia × 2 workers × (pool 3 + overflow 2) = 10 conexiones ≪ 35 de B1ms.
- Instrucciones del operador (INSTRUCCIONES_CLAUDE.md, UDL) piden FastAPI.

## Consecuencias
- Costo fijo ~US$13/mes (B1) en lugar de Flex Consumption.
- OpenAPI/Swagger solo en `APP_ENV=local`.
- Rol de BD de la app (`exam_app`) distinto del propietario; sin DDL.
