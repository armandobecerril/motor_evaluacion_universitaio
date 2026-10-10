# 02 — Arquitectura técnica

> Actualizado por ADR-001 (PostgreSQL), ADR-002 (Python Functions), ADR-003 (multi-universidad) y ADR-004 (acceso alumno). Azure SQL Database ya no forma parte de la solución.

## Stack
- **Frontend:** React + Vite + TypeScript en Azure Static Web Apps (Standard, con backend vinculado).
- **API:** Azure Functions **Python 3.12** (modelo v2, plan Flex Consumption). Sin acceso directo a BD desde el frontend.
- **Datos:** Azure Database for PostgreSQL – Flexible Server (PG 16/17), SQLAlchemy 2 + Alembic, Row-Level Security por universidad.
- **Identidad:** Microsoft Entra ID para docentes y administradores. Alumnos: universidad + matrícula + código de convocatoria contra lista autorizada (ADR-004); **no equivale a identidad verificada**.
- **Observabilidad:** Application Insights con PII minimizada, trazas correlacionadas y alertas.
- **IaC:** Bicep. **CI/CD:** GitHub Actions con federación OIDC. El operador ejecuta manualmente `git push` y los comandos `az` (Claude entrega los comandos uno a uno).

## Estructura del repositorio
- `apps/web`: rutas `/`, `/ingresar`, `/examen`, `/fin`, `/admin`, `/admin/banco`, `/admin/resultados`.
- `apps/api`: `function_app.py`; paquete `exam_engine` (config, db, models, http/*, servicios de scoring, deadline, sampler, auditoría); `migrations/` (Alembic); `tests/`.
- `bank/`: banco en revisión (JSON/CSV) y reporte de calidad; nunca se empaqueta en el frontend.
- `infra/`: Bicep por ambiente (H5). `docs/`: especificación y ADRs.

## API propuesta
Alumno: POST `/api/student/session` (universidad, matrícula, código; rate limit); POST `/api/attempts` (inicio atómico); GET `/api/attempts/me/current` (solo pregunta actual, opciones y deadline); POST `/api/attempts/me/answer` (ordinal, opción u omisión, idempotency key); POST `/api/attempts/me/finish`; GET `/api/attempts/me/receipt`.
Admin (Entra ID, autorización por rol y materia en cada endpoint): POST `/api/admin/bank/import`, GET `/api/admin/bank/quality`, POST `/api/admin/bank/approve`, POST `/api/admin/bank/publish`, CRUD `/api/admin/exam-versions`, roster, GET `/api/admin/sessions`, GET `/api/admin/results.csv`. Plataforma: CRUD `/api/platform/institutions`, `/api/platform/subjects`.
Salud: GET `/api/health` (sin secretos; reporta BD y versión de migración).

## Principios
La API valida universidad, identidad, intento, pregunta, deadline y estado en cada operación. La base guarda snapshots del orden de preguntas/opciones y de la versión del banco. No se entregan preguntas futuras ni claves al cliente. Dos roles de BD: propietario (migraciones) y `exam_app` (DML, sujeto a RLS). Conexión TLS; autenticación con Entra ID para PostgreSQL cuando sea viable, si no contraseña en Key Vault. CORS estricto, cabeceras seguras, CSP, acceso mínimo y backups.

## Conexiones
B1ms admite 35 conexiones de usuario y no incluye PgBouncer. Por instancia: pool 3 + overflow 2; máximo 6 instancias. Para el examen: escalar a General Purpose (PgBouncer disponible) y 1 instancia "always ready".
