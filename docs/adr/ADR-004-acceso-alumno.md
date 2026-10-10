# ADR-004 — Acceso del alumno: matrícula + código de convocatoria

- **Estado:** aceptado por el operador (2026-10-09), con riesgo documentado

## Decisión
El alumno ingresa con **código de universidad + matrícula + código de convocatoria**.

## Controles obligatorios
- Solo matrículas cargadas en `exam_version_roster` pueden iniciar; `allowed_attempts` (por defecto 1).
- El código de convocatoria se guarda con hash (`exam_versions.access_code_hash`), nunca en claro.
- Al iniciar, el servidor emite un token de intento aleatorio; solo se guarda su hash (`exam_sessions.token_hash`). Las peticiones posteriores usan ese token, no la matrícula.
- Rate limiting por IP y por matrícula; bloqueo temporal tras intentos fallidos; todo en `audit_events`.
- La convocatoria solo acepta ingresos dentro de su ventana y si está `enabled`.

## Riesgo aceptado
Este mecanismo **no verifica la identidad** del alumno: quien conozca matrícula y código puede presentar en su lugar. Mitigaciones: código distinto por convocatoria y grupo, ventana corta, supervisión presencial o por videollamada, y conciliación de la lista de asistencia con los intentos. Migrar a SSO institucional o token individual cuando la universidad lo permita.
