# Motor de Evaluación Universitario

Plataforma de exámenes en línea para varias universidades y materias. Primera materia: **Sistemas Informáticos Aplicados a Finanzas (SIAF)**, MBA.

- Frontend: React + Vite + TypeScript (`apps/web`) → Azure Static Web Apps.
- API: Azure Functions Python 3.12 (`apps/api`) → Flex Consumption.
- Datos: PostgreSQL 16/17 (Azure Database for PostgreSQL Flexible Server), SQLAlchemy 2 + Alembic, Row-Level Security por universidad.
- Decisiones: `docs/adr/`. Especificación: `docs/01..09`. Auditoría inicial y costos: `docs/00_AUDITORIA_H0.md`.

> Estado: **H1** (estructura, modelo de datos, migraciones, health, CI). El motor de examen (H2), el panel docente (H3), el banco de 480 reactivos (H4) e IaC (H5) aún no están implementados.

## Requisitos locales (macOS)
- Python 3.12 (`python3.12 --version`). Con conda: `conda create -n motor python=3.12 -y && conda activate motor`.
- Node 20 o 22 (`node --version`).
- PostgreSQL 16 o 17, una de dos opciones:
  - **Docker:** `docker compose up -d db` (crea `exam_dev`, `exam_test` y el rol `exam_app` con contraseñas de desarrollo).
  - **Homebrew:** ver “PostgreSQL con Homebrew” abajo.

## Primer arranque
```bash
# 1. Variables locales (no se suben al repo)
cp .env.example apps/api/.env
#    Edita apps/api/.env y sustituye CAMBIAR (con docker compose: exam_owner=devpass, exam_app=apppass)

# 2. Dependencias
make setup

# 3. Esquema y catálogo SIAF de demostración
make migrate
make seed

# 4. Pruebas (API: lint + integración contra PostgreSQL; Web: lint, tipos, pruebas, build y escaneo del bundle)
make test

# 5. Frontend en desarrollo
cd apps/web && npm run dev      # http://localhost:5173
```
Para correr la API localmente con Azure Functions Core Tools (opcional en H1):
```bash
cp apps/api/local.settings.example.json apps/api/local.settings.json   # y ajusta DATABASE_URL
cd apps/api && source .venv/bin/activate && func start                  # http://localhost:7071/api/health
```

## PostgreSQL con Homebrew
```bash
brew install postgresql@17
brew services start postgresql@17
createuser -s "$USER" 2>/dev/null || true
psql postgres -c "CREATE ROLE exam_owner LOGIN PASSWORD 'devpass' CREATEDB;"
psql postgres -c "CREATE DATABASE exam_dev OWNER exam_owner;"
psql postgres -c "CREATE DATABASE exam_test OWNER exam_owner;"
psql postgres -c "CREATE ROLE exam_app LOGIN PASSWORD 'apppass' NOSUPERUSER NOBYPASSRLS;"
```

## Roles de base de datos
| Rol | Uso | Variable |
|---|---|---|
| propietario (`exam_owner`) | Migraciones Alembic (DDL) | `MIGRATION_DATABASE_URL` |
| `exam_app` | API: solo DML, sujeto a RLS, sin BYPASSRLS | `DATABASE_URL` |

En Azure, `exam_app` se crea con `apps/api/scripts/bootstrap_roles.sql` antes de migrar.

## Estructura
```
apps/api      Functions Python: exam_engine/ (config, db, models, http), migrations/, tests/, scripts/, seeds/
apps/web      React + Vite + TS, escaneo del bundle (scripts/check-bundle.mjs)
bank/         Banco en revisión (JSON/CSV) — nunca se empaqueta en el frontend
docs/         Especificación, ADRs, auditoría
infra/        Bicep (H5)
.github/      CI (lint, pruebas con PostgreSQL 17, escaneo de secretos), Dependabot
```

## Reglas del proyecto
- Sin claves de respuesta en el frontend ni en respuestas de API para alumnos; calificación solo en servidor.
- Sin secretos ni PII en el repositorio; los PDF académicos quedan fuera (`.gitignore`).
- El operador ejecuta personalmente `git push` y todos los comandos `az`.
