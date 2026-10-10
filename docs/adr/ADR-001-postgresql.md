# ADR-001 — PostgreSQL como base de datos oficial

- **Estado:** aceptado (2026-10-09)
- **Reemplaza:** Azure SQL Database (mencionado en la versión original de los documentos)

## Decisión
Usar **Azure Database for PostgreSQL – Flexible Server** (PostgreSQL 16 o 17; objetivo 17) en lugar de Azure SQL Database. Persistencia con **SQLAlchemy 2** y migraciones con **Alembic**.

## Contexto
Plataforma de evaluación académica con hasta 30 estudiantes concurrentes por convocatoria, banco inicial de 480 preguntas, 200 reactivos por intento y temporizador de 20 segundos.

## Requisitos técnicos
- Pool de conexiones limitado y compatible con el hosting (ver ADR-002: instancias máx × (pool + overflow) < 35 en B1ms).
- Índices para matrícula, convocatoria, intento y pregunta.
- Transacciones atómicas para registrar respuestas; unicidad para impedir respuestas duplicadas; idempotencia ante reintentos.
- Calificación exclusivamente del lado del servidor.
- TLS (`sslmode=require`) y secretos fuera del repositorio.
- Backups automáticos y procedimiento de restauración probado.
- Prueba de carga con al menos 30 usuarios concurrentes antes de cada examen.

## Modelo mínimo
`students`, `exam_versions`, `exam_sessions`, `questions`, `question_options`, `exam_session_questions`, `answers`, `exam_results`, `audit_events`, `administrators` — ampliado por ADR-003 (multi-universidad) con `institutions`, `subjects`, `subject_modules`, `subject_sources`, `administrator_subjects`, `bank_publications`, `bank_publication_questions`, `exam_version_pool`, `exam_version_roster`.

## Reglas críticas
1. El frontend nunca recibe respuestas correctas.
2. Cada intento conserva una selección inmutable de preguntas.
3. El temporizador se valida con la hora del servidor.
4. Cada respuesta se guarda mediante una operación atómica e idempotente.
5. Las calificaciones se calculan en el backend.
6. Los exámenes en curso no se ven afectados por una nueva publicación del banco (`bank_publications`).
7. Las migraciones son versionadas y reversibles cuando sea viable.

## Notas de dimensionamiento
- B1ms (Burstable): 35 conexiones de usuario y **sin PgBouncer integrado**. Para el día del examen se recomienda escalar temporalmente a General Purpose (D2ds_v5) y regresar a B1ms al terminar.
