# ADR-006 — Formato del banco maestro y selección del examen (UDL SIAF Parcial 1)

- **Estado:** aceptado por el operador (2026-10-10), con riesgos documentados

## Formato
JSON `{ metadata, questions[] }` (formato UDL) o CSV equivalente. Campos por reactivo: `id`, `universidad`, `materia`, `examen`, `module`, `topic`, `bloom`, `difficulty`, `stem`, `options[A–D]`, `correct_option_id`, `rationale`, `source_pdf`, `source_page` (puede ser nulo), `conceptual_group` **o** `concept_id`, `variant`, `case_type`, `status`.
- Importación **todo o nada**, idempotente por `id`; contenido distinto ⇒ nueva versión (la anterior se conserva) y evento de auditoría. `metadata` se guarda sin alterar en `question_imports`.
- Todo entra como `draft`; solo el docente aprueba.
- Se rechaza: universidad o materia distinta a la destino, módulo inexistente, fuente no registrada o de solo inspiración (MoNeT, Knight Capital), página fuera de rango, opciones ≠ 4, clave fuera de A–D, ids duplicados.

## Selección (decisión del operador)
- Banco UDL: 400 reactivos = 100 conceptos × 4 casos; 100 por módulo, 25 conceptos por módulo.
- Cada alumno recibe **200 preguntas al azar, 50 por módulo**, en orden propio y con opciones barajadas.
- Como 50 > 25 conceptos por módulo, la regla "un concepto por intento" (INSTRUCCIONES punto 6) es imposible con este banco. El operador decidió no bloquear. Para que no sea una relajación silenciosa, el parámetro es explícito y visible: `max_variants_per_group = 2` y `selection = balanced_by_group` (2 de los 4 casos de cada concepto, elegidos al azar). Así cada alumno cubre los 100 conceptos exactamente dos veces.

## Riesgos aceptados (ver `bank/reporte_calidad_UDL_SIAF_P1.md`)
1. En los 100 conceptos la respuesta correcta repite la misma frase central entre casos: la segunda aparición del concepto queda prácticamente resuelta por la primera.
2. ~114 palabras por reactivo en 20 s ≈ 340 palabras/min, por encima de la lectura típica (200–250). Recomendación: piloto con alumnos; considerar 30–35 s o acortar enunciados.
3. En 84 % de los reactivos la correcta es la opción más larga.
4. Ningún reactivo cita página; el sustento por página debe verificarlo el docente.
