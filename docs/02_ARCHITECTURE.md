# 02 — Arquitectura técnica

> Actualizado por ADR-001 (PostgreSQL), ADR-002 (FastAPI en App Service), ADR-003 (multi-universidad), ADR-004 (acceso alumno), ADR-005 (acceso docente) y ADR-006 (banco y selección). Azure SQL Database y Azure Functions ya no forman parte de la solución.

## Stack
- **Frontend:** React + Vite + TypeScript en Azure Static Web Apps (Standard, con App Service como backend vinculado).
- **API:** **FastAPI, Python 3.12** en Azure App Service Linux B1 (gunicorn + uvicorn). Sin acceso directo a BD desde el frontend.
- **Datos:** Azure Database for PostgreSQL – Flexible Server (PG 16/17), SQLAlchemy 2 + Alembic, Row-Level Security por universidad.
- **Identidad:** docentes con usuario y contraseña (ADR-005; Entra ID opcional a futuro). Alumnos: código del examen + nombre completo + matrícula (ADR-004); **no equivale a identidad verificada**.
- **Observabilidad:** Application Insights con PII minimizada, trazas correlacionadas y alertas.
- **IaC:** Bicep. **CI/CD:** GitHub Actions con federación OIDC. El operador ejecuta manualmente `git push` y los comandos `az` (Claude entrega los comandos uno a uno).

## Estructura del repositorio
- `apps/web`: rutas `/`, `/ingresar`, `/examen`, `/fin`, `/admin`, `/admin/banco`, `/admin/resultados`.
- `apps/api`: paquete `exam_engine` (`main.py` FastAPI, `api/` routers, `services/` importador, calidad, autenticación y —en H2— selección, deadline y scoring; `models.py`, `db.py`, `cli.py`); `migrations/` (Alembic); `seeds/`; `tests/`.
- `bank/`: banco en revisión (JSON/CSV) y reporte de calidad; nunca se empaqueta en el frontend.
- `infra/`: Bicep por ambiente (H5). `docs/`: especificación y ADRs.

## API propuesta
Alumno: POST `/api/student/session` (código del examen, nombre completo, matrícula; rate limit); POST `/api/attempts` (inicio atómico); GET `/api/attempts/me/current` (solo pregunta actual, opciones y deadline); POST `/api/attempts/me/answer` (ordinal, opción u omisión, idempotency key); POST `/api/attempts/me/finish`; GET `/api/attempts/me/receipt`.
Docente (sesión por cookie, autorización por rol y materia en cada endpoint). Implementados: POST `/api/admin/login`, `/logout`, `/password`; GET `/api/admin/me`, `/catalog`; POST `/api/admin/courses/{id}/bank/validate` (en seco + reporte de calidad), `/bank/import`; GET `/bank/summary`. Pendientes (H2/H3): revisión y aprobación de reactivos, CRUD de exámenes, publicación con código de acceso, monitoreo, `results.csv`.
Salud: GET `/api/health` (sin secretos; reporta BD y versión de migración).

## Principios
La API valida universidad, identidad, intento, pregunta, deadline y estado en cada operación. La base guarda snapshots del orden de preguntas/opciones y de la versión del banco. No se entregan preguntas futuras ni claves al cliente. Dos roles de BD: propietario (migraciones) y `exam_app` (DML, sujeto a RLS). Conexión TLS; contraseña del rol `exam_app` y `ACCESS_CODE_PEPPER` en Key Vault (referencias de App Settings). CORS estricto, cabeceras seguras, CSP, acceso mínimo y backups.

## Conexiones
B1ms admite 35 conexiones de usuario y no incluye PgBouncer. App Service B1: 1 instancia × 2 workers × (pool 3 + overflow 2) = 10 conexiones. Para el examen se puede escalar PostgreSQL a General Purpose y regresar al terminar.
