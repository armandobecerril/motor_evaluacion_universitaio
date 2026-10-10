# ADR-002 — Backend en Azure Functions con Python

- **Estado:** aceptado (2026-10-09)
- **Reemplaza:** Azure Functions TypeScript

## Decisión
API en **Azure Functions, Python 3.12, modelo de programación v2**, plan **Flex Consumption**. El frontend se mantiene en React + Vite + TypeScript (Azure Static Web Apps con backend vinculado).

## Motivo
ADR-001 exige SQLAlchemy 2 y Alembic (Python). Mantener TypeScript implicaría dos lenguajes en el backend o abandonar Alembic.

## Consecuencias
- Contratos API: modelos Pydantic en el backend; los tipos TypeScript del frontend se mantienen manualmente en `apps/web/src/lib/api.ts` (o se generan desde OpenAPI en un hito posterior).
- Pool por instancia: `DB_POOL_SIZE=3`, `DB_MAX_OVERFLOW=2`, máximo de instancias Flex = 6 en B1ms (6 × 5 = 30 < 35).
- Arranque en frío: configurar 1 instancia "always ready" durante la ventana del examen.
- Rol de BD de la app (`exam_app`) distinto del rol propietario de migraciones; sin DDL.
