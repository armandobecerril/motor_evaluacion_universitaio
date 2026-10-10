# ADR-003 — Plataforma multi-universidad y multi-materia

- **Estado:** aceptado (2026-10-09)

## Decisión
Una sola instalación atiende a varias universidades (`institutions`) y materias (`subjects`). La primera materia configurada es **Sistemas Informáticos Aplicados a Finanzas (SIAF)**.

## Reglas
- Jerarquía: Universidad → Materia → Módulos → Banco → Convocatorias → Intentos.
- Toda tabla con datos de una universidad tiene `institution_id`. Las llaves foráneas compuestas `(id, institution_id)` impiden referencias cruzadas entre universidades.
- **Row-Level Security** (FORCE) en PostgreSQL como segunda barrera: la API fija `app.institution_id` por transacción (`set_config(..., true)`); sin contexto no se ve ninguna fila. Solo endpoints de administración de plataforma usan `app.platform_admin = on`.
- Parámetros de la materia (número de módulos, meta del banco por módulo, tamaño del examen, cuota por módulo, segundos por pregunta, scoring, ventana, tolerancia de red, cuotas Bloom) se guardan en `subjects.config` y se congelan en `exam_versions.config` al abrir una convocatoria. Nada de SIAF queda escrito en código.
- Matrícula única **por universidad** (`UNIQUE(institution_id, matricula)`).
- Roles: `platform_admin`, `institution_admin`, `teacher` (alcance por materia en `administrator_subjects`).
- Fuentes académicas registradas por materia (`subject_sources`) con uso `question_source` o `scenario_inspiration` y marca de derechos restringidos.
