# 03 — Modelo de datos y contratos

> Fuente de verdad: `apps/api/exam_engine/models.py` y `apps/api/migrations/`. PostgreSQL (ADR-001), multi-universidad (ADR-003). Nombres de tabla según INSTRUCCIONES (UDL).

## Tablas
**Catálogo**
- `universities`: code UNIQUE, name, active. (Sin RLS.)
- `courses` (materias): university_id, code, name, `config` JSONB (parámetros por defecto de exámenes); UNIQUE(university_id, code).
- `course_modules`: module_number, name; UNIQUE(course_id, module_number).
- `course_sources`: PDF autorizados: file_name, page_count, module_number, usage (`question_source` | `scenario_inspiration`), copyright_restricted.

**Personas**
- `administrators`: username UNIQUE, password_hash (Argon2id), must_change_password, entra_object_id (opcional), role (`platform_admin` | `university_admin` | `teacher`), failed_logins, locked_until; university_id NULL solo para platform_admin.
- `administrator_courses`: alcance de cada docente. `admin_sessions`: hash del token de sesión, expiración, revocación.
- `students`: matrícula + nombre; UNIQUE(university_id, matricula). Se crea al primer ingreso (registro libre).

**Banco**
- `question_imports`: cada archivo importado (bank_code, sha256, `source_metadata` sin alterar, conteos, quién y cuándo).
- `question_bank`: external_id, version, is_current (índice único parcial: una vigente por id), module_number, topic, bloom, difficulty, stem, rationale, source_id, source_page (nullable), conceptual_group, variant, case_type, status (`draft`→`reviewed`→`approved`→`retired`), checksum, reviewer, reviewed_at.
- `question_options`: A–D, text, is_correct (solo BD/API docente); máx. 1 correcta (índice parcial).

**Exámenes e intentos**
- `exams`: course_id, code (p. ej. PARCIAL-1), name, starts_at/ends_at, status (`draft`/`published`/`closed`/`cancelled`), `access_code_lookup` (HMAC del código, UNIQUE), `config` JSONB congelado, published_at/by.
- `exam_questions`: pool congelado al publicar (versiones exactas de reactivos aprobados).
- `exam_attempts`: student_id, attempt_number, full_name_entered, status, started_at, window_deadline_at, finished_at, current_ordinal, seed, config_snapshot, token_hash UNIQUE, row_version; UNIQUE(exam_id, student_id, attempt_number).
- `attempt_questions`: (attempt_id, ordinal) PK, question_id, module_number, options_order, served_at, deadline_at, state; UNIQUE(attempt_id, question_id).
- `attempt_answers`: UNIQUE(attempt_id, ordinal), UNIQUE(attempt_id, idempotency_key), outcome, selected_option_id coherente. Append-only.
- `attempt_results`: total, correct, wrong, omitted, expired, raw_score, grade (0–100); CHECK suma = total.
- `audit_events`: actor, attempt_id, event_type, metadata (sin claves ni secretos). Append-only.
- `access_throttle`: contadores por ventana para límites de intentos de ingreso.

## Integridad aplicada por la base
- RLS FORCE en tablas con `university_id`; llaves foráneas compuestas `(id, university_id)`.
- Trigger: un reactivo solo se aprueba con 4 opciones, 1 correcta, reviewer y reviewed_at; aprobado ⇒ inmutable (salvo pasar a `retired` o dejar de ser vigente); sus opciones también.
- Triggers append-only en `attempt_answers` y `audit_events`.

## Contratos
- DTO de alumno: id opaco, enunciado, opciones reordenadas (sin `is_correct`), ordinal, deadline del servidor. Nunca `rationale`, `correct_option_id`, `source_*`.
- Formato del banco e importación: ver ADR-006.
