# ADR-004 — Acceso del alumno: código del examen + nombre completo + matrícula

- **Estado:** aceptado por el operador (2026-10-09), con riesgo documentado

## Decisión (actualizada 2026-10-10)
Cada examen tiene **un único código de acceso**. El alumno escribe **código + nombre completo + matrícula** (registro libre, sin lista previa). Un intento por matrícula y examen.

## Controles obligatorios
- El código identifica al examen y a su universidad; se guarda como HMAC (`exams.access_code_lookup`), nunca en claro. Se muestra al docente al publicar y puede regenerarse.
- `UNIQUE(exam_id, student_id, attempt_number)`: una matrícula no puede reintentar sin autorización auditada.
- Al iniciar, el servidor emite un token de intento aleatorio; solo se guarda su hash (`exam_attempts.token_hash`). Las peticiones posteriores usan ese token.
- Se guarda el nombre tecleado en cada intento (`full_name_entered`) para conciliar con la lista oficial.
- Rate limiting por IP y por matrícula; todo en `audit_events`.
- El examen solo acepta ingresos dentro de su fecha/hora y si está `published`.

## Riesgo aceptado
Este mecanismo **no verifica la identidad** del alumno: quien conozca el código y una matrícula puede presentar en su lugar, y una matrícula ajena usada primero bloquea al alumno legítimo. Mitigaciones: ventana corta, supervisión presencial o por videollamada, conciliación de nombres y matrículas con la lista oficial (exportación CSV) y anulación/reapertura auditada por el docente. Migrar a SSO institucional o token individual cuando la universidad lo permita.
