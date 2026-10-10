# 03 — Modelo de datos y contratos

> Fuente de verdad: `apps/api/exam_engine/models.py` y `apps/api/migrations/`. PostgreSQL (ADR-001), multi-universidad (ADR-003).

## Tablas
**Catálogo**
- `institutions`: id, code UNIQUE, name, active. (Sin RLS: se usa para resolver la universidad al ingresar.)
- `subjects`: institution_id, code, name, `config` JSONB (parámetros por defecto), UNIQUE(institution_id, code).
- `subject_modules`: subject_id, module_number, name, bank_target (p. ej. 120), UNIQUE(subject_id, module_number).
- `subject_sources`: PDF autorizados por materia: file_name, page_count, usage (`question_source` | `scenario_inspiration`), copyright_restricted.

**Personas**
- `administrators`: entra_object_id UNIQUE, email, display_name, role (`platform_admin` | `institution_admin` | `teacher`); institution_id NULL solo para platform_admin.
- `administrator_subjects`: alcance de cada docente por materia.
- `students`: matricula, full_name, email, group_name; UNIQUE(institution_id, matricula). PII mínima.

**Banco**
- `questions`: subject_id, module_id, external_id, version, topic, bloom, difficulty, stem, rationale, source_id, source_page, conceptual_group, status (`draft`→`reviewed`→`approved`→`retired`), checksum, author, reviewer, reviewed_at; UNIQUE(subject_id, external_id, version).
- `question_options`: option_code A–D, text, is_correct (solo BD/API admin); UNIQUE(question_id, option_code); índice único parcial: máx. 1 correcta.
- `bank_publications` + `bank_publication_questions`: versión congelada del banco aprobado de una materia.

**Convocatorias e intentos**
- `exam_versions` (convocatorias A/B…): subject_id, publication_id, code, ventana starts_at/ends_at, enabled, access_code_hash, `config` JSONB congelado, config_version.
- `exam_version_pool`: preguntas asignadas a la convocatoria (allocation_tag) — permite pools disjuntos A/B.
- `exam_version_roster`: matrículas autorizadas, allowed_attempts.
- `exam_sessions` (intentos): student_id, exam_version_id, attempt_number, status, started_at, window_deadline_at, finished_at, current_ordinal, seed, config_snapshot, token_hash UNIQUE, row_version; UNIQUE(exam_version_id, student_id, attempt_number).
- `exam_session_questions`: (session_id, ordinal) PK, question_id, module_number, options_order, served_at, deadline_at, state; UNIQUE(session_id, question_id).
- `answers`: UNIQUE(session_id, ordinal), UNIQUE(session_id, idempotency_key), outcome (`correct`,`wrong`,`omitted`,`expired`), selected_option_id coherente con outcome. Append-only.
- `exam_results`: total, correct, wrong, omitted, expired, raw_score, grade (0–100), scoring_version; CHECK suma = total.
- `audit_events`: actor_type, actor_id, session_id, event_type, occurred_at, metadata (sin claves ni secretos). Append-only.

## Integridad aplicada por la base
- RLS FORCE en todas las tablas con `institution_id`; llaves foráneas compuestas `(id, institution_id)`.
- Trigger: solo se aprueba un reactivo con exactamente 4 opciones y 1 correcta, y con reviewer + reviewed_at.
- Trigger: un reactivo aprobado es inmutable (salvo pasar a `retired`); sus opciones también. Correcciones = nueva versión.
- Triggers append-only en `answers` y `audit_events`.

## Contratos
- `studentQuestionDTO`: id opaco, texto, opciones reordenadas (sin `is_correct`), ordinal, deadline del servidor.
- El importador rechaza IDs duplicados, páginas inexistentes (`source_page` > `page_count`), fuentes fuera de `subject_sources`, fuentes de uso `scenario_inspiration` como cita, ambigüedad marcada y reactivos sin revisión. Importación en staging + transacción.
- `source_pdf`/`source_page` no se publican al estudiante.

## Ejemplo de reactivo (solo ilustrativo, no cuenta en los 480)
```json
{"id":"MBA-SIAF-DEMO-0001","module":4,"topic":"RPA vs API","bloom":"evaluar","difficulty":"media","stem":"Dos sistemas modernos ofrecen APIs estables. ¿Qué integración conviene evaluar primero?","options":[{"id":"A","text":"Un bot que copie datos"},{"id":"B","text":"Una API entre sistemas"},{"id":"C","text":"Una hoja manual"},{"id":"D","text":"Reemplazar ambos sistemas"}],"correct_option_id":"B","rationale":"API-first cuando exista una integración adecuada.","source_pdf":"04_AUTOMATIZACION-FINANCIERA.pdf","source_page":10,"conceptual_group":"API_FIRST","status":"draft"}
```
