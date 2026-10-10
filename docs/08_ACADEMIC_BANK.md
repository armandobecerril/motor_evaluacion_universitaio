# 08 — Protocolo para producir 480 reactivos reales

## Fuentes autorizadas
1. `01_Sistemas-de-Informacion-en-la-Funcion-Financiera.pdf` (15 páginas): módulo 1.
2. `02_Arquitectura-Empresarial.pdf` (23 páginas): módulo 2.
3. `03_El-ERP.pdf` (30 páginas): módulo 3.
4. `04_AUTOMATIZACION-FINANCIERA.pdf` (22 páginas): módulo 4.
5. `01_Caso_BMV_MoNeT.pdf` (1 página): inspiración transversal, NO preguntas sobre el caso.
6. `01_Knight Capital(1).pdf` (11 páginas, derechos reservados): inspiración transversal, NO reproducir ni redistribuir texto o hechos identificables del caso.

## Temas orientativos — verificar contra PDFs, NO suponer cobertura
- M1: datos operativos y decisión del CFO, sistemas financieros, integración, información, valor, riesgo y calidad de datos.
- M2: arquitectura empresarial, capacidades, componentes, dependencias, criterios de elección, gobernanza y decisiones de inversión.
- M3: ERP vs marca, FI/CO/MM/SD/PP/Tesorería, GL/AR/AP, compra/construcción/híbrido, roadmap por dolor de negocio, KPI DIO/DSO/OTIF, TCO y riesgos.
- M4: digitalización vs automatización, RPA, APIs, integración de datos/aplicaciones/procesos, AS-IS/TO-BE, STP, excepciones, controles, KPI, segregación de funciones, riesgos de automatizar errores.

## Proceso de creación
1. Extraer contenido por página y registrar matriz tema→páginas. Inspeccionar visuales/diagramas que no se extraigan bien.
2. Elaborar blueprint 120 preguntas por módulo, con subtemas y Bloom/dificultad.
3. Crear lotes de 30–40 preguntas en JSON, cada una con fuente, página y justificación; evitar afirmaciones no respaldadas.
4. Validar esquema, unicidad semántica, respuesta única, dificultad y tiempo de lectura. Dos alternativas pueden parecer plausibles, pero SOLO una debe ser superior por condiciones explícitas.
5. Revisar por docente; pasar de `draft` a `reviewed` y luego `approved` con nombre/fecha. No autoaprobar.
6. Exportar `bank/questions.review.json`, `bank/questions.review.csv` y `bank/quality_report.md`. El JSON de claves se almacena solo en backend seguro.

## Estilo
Lenguaje de MBA, multidisciplinario, español claro. Escenarios de empresas inventadas (salud, retail, manufactura, logística, universidad, fintech, servicios). Evitar preguntas triviales, trampas ambiguas, datos numéricos no enseñados, nombres de casos reales y detalles de programación. 20 segundos: enunciado preferente 20–45 palabras y opciones breves; probar empíricamente.

## Contrato JSON
Campos: `id`, `module`, `topic`, `bloom`, `difficulty`, `stem`, `options` (4 `{id,text}`), `correct_option_id`, `rationale`, `source_pdf`, `source_page`, `conceptual_group`, `status`, `reviewer`, `reviewed_at`. No dejar campos vacíos salvo reviewer/fecha para borradores.

## Validación de 480
Si no existen 480 preguntas distintas de calidad sustentadas en PDFs, informar cuántas sí hay y solicitar decisión docente. Nunca duplicar con cambios cosméticos. Si la cobertura de una sesión no soporta 120 preguntas realmente diferenciadas, proponer ajustes de distribución antes de generar.
