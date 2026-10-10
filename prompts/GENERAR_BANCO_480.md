# Prompt operativo para Claude — generación de banco

Lee `docs/08_ACADEMIC_BANK.md` y los PDF de `source_materials/`. Produce 480 preguntas de calidad, 120 por módulo, en lotes de 30–40. Primero genera mapa de temas por PDF/página y blueprint de cobertura. Después genera un lote por ejecución, lo valida y guarda cambios incrementalmente en `bank/questions.review.json`; añade `bank/quality_report.md`. No inventes preguntas fuera de las fuentes ni afirmes que se generaron 480 si no se verificó el conteo.

Cada pregunta: 4 opciones, 1 única mejor respuesta, explicación y cita PDF/página. Distribuye Bloom 15/25/30/30 y dificultades; contextos ficticios, decisión ejecutiva, texto resoluble en 20s. Casos MoNeT/Knight Capital: solo inspiración conceptual, sin preguntas directas ni reproducción. No autoaprobar preguntas; status `draft` hasta revisión docente. Después de cada lote muestra 10 muestras, duplicados, ambigüedades y progreso por módulo.
