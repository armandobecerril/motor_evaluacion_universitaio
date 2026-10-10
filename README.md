# Motor de Evaluación Universitario

Plataforma de exámenes en línea para varias universidades y materias. Primer caso: **UDL · Sistemas Informáticos Aplicados a Finanzas · Parcial 1**.

- Frontend: React + Vite + TypeScript (`apps/web`) → Azure Static Web Apps.
- API: FastAPI, Python 3.12 (`apps/api`) → Azure App Service Linux.
- Datos: PostgreSQL 16/17 (Azure Database for PostgreSQL Flexible Server), SQLAlchemy 2 + Alembic, Row-Level Security por universidad.
- Decisiones: `docs/adr/`. Especificación: `docs/01..09`. Auditoría y costos: `docs/00_AUDITORIA_H0.md`.

## Estado
| Hito | Estado |
|---|---|
| H1 estructura, modelo multi-universidad, migración, CI | ✔ |
| Acceso docente (usuario/contraseña), importador del banco + reporte de calidad, panel docente (subir y validar banco) | ✔ |
| H2 revisión/aprobación, crear examen con fecha + código de acceso único, motor del alumno (selección balanceada, reloj del servidor, omitir, +1/−1/0, reanudación) | ✔ |
| H3 calificaciones en vivo (cada 10 s) y CSV para Excel | ✔ (pendiente: anulación/reapertura auditada de intentos) |
| H5 Bicep, prueba de carga (30 usuarios), guías · H6 despliegue | pendiente |

## Requisitos locales (macOS)
- Python 3.12 (`python3.12 --version`; con conda: `conda create -n motor python=3.12 -y && conda activate motor`).
- Node 20 o 22.
- PostgreSQL 16 o 17: `docker compose up -d db` **o** Homebrew (abajo).

## Primer arranque
```bash
cp .env.example apps/api/.env          # edita: sustituye CAMBIAR (docker compose: exam_owner=devpass, exam_app=apppass)
make setup                             # venv + dependencias API y web
make migrate                           # esquema (Alembic)
make seed                              # UDL / SIAF: 4 módulos y 6 fuentes (sin preguntas)
make admin                             # crea el usuario docente 'admin' (pide la contraseña)
make test                              # pruebas API (con PostgreSQL) y web
make api                               # API en http://localhost:8000  (docs: /api/docs)
make web                               # en otra terminal: http://localhost:5173/admin
```
Para que el docente cambie la contraseña en su primer ingreso: `make admin TEMP=1`.

Reporte de calidad de un banco sin base de datos:
```bash
cd apps/api && .venv/bin/python -m exam_engine.cli bank-report ruta/banco.json --quota 50 --max-variants 2 --seconds 20
```

## PostgreSQL con Homebrew
```bash
brew install postgresql@17 && brew services start postgresql@17
psql postgres -c "CREATE ROLE exam_owner LOGIN PASSWORD 'devpass' CREATEDB;"
psql postgres -c "CREATE DATABASE exam_dev OWNER exam_owner;"
psql postgres -c "CREATE DATABASE exam_test OWNER exam_owner;"
psql postgres -c "CREATE ROLE exam_app LOGIN PASSWORD 'apppass' NOSUPERUSER NOBYPASSRLS;"
```

## Roles de base de datos
| Rol | Uso | Variable |
|---|---|---|
| propietario (`exam_owner`) | Migraciones (DDL) | `MIGRATION_DATABASE_URL` |
| `exam_app` | API: solo DML, sujeto a RLS | `DATABASE_URL` |

## Flujo de uso
1. **Docente** (`/admin`): elige materia → *Banco*: sube el JSON/CSV, valida e importa → *Revisión*: aprueba preguntas → *Exámenes*: crea el examen (fecha, segundos, preguntas por módulo, penalización) y pulsa **Publicar y generar código**.
2. **Alumno** (`/ingresar`): código de acceso + nombre completo + matrícula → reglas → examen. Cada respuesta se guarda al instante; si recarga, continúa donde iba sin tiempo extra.
3. **Docente** → *Ver calificaciones*: tabla en vivo y **Descargar CSV (Excel)**.

## Banco de preguntas
- Se sube desde el panel docente (`/admin`) o se valida con el CLI. Formato: ADR-006.
- **Los archivos con respuestas no van al repositorio**: guárdalos en `bank/private/` (ignorado por Git).
- `bank/reporte_calidad_UDL_SIAF_P1.md`: reporte del banco del Parcial 1 (sin claves).

## Reglas del proyecto
- Sin claves de respuesta en el frontend ni en respuestas para alumnos; calificación solo en servidor.
- Sin secretos ni PII en el repositorio; PDFs fuera (`.gitignore`).
- El operador ejecuta personalmente `git push` y los comandos `az`.
