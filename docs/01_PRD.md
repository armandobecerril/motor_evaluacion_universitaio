# 01 — Producto y requisitos (PRD)

## Propósito
Examen parcial 1, MBA Sistemas Informáticos Aplicados a Finanzas. Público multidisciplinario; evaluar criterio financiero y ejecutivo, no programación.

## Parámetros
- Banco objetivo: 480 reactivos únicos, 120 por cada una de cuatro sesiones.
- Cada intento: 200 reactivos, exactamente 50 por sesión, con mezcla de temas y posiciones de opciones.
- 20 segundos por reactivo, avance automático; 66:40 minutos efectivos. Ventana administrativa propuesta de 80 minutos (incluye registro, instrucciones y cierre), configurable.
- Correcta +1; incorrecta −1; omitida 0. Nota = max(0, 100*(aciertos−errores)/200), redondeada a dos decimales solo para visualización.
- Respuesta única seleccionable, pero permitir omitir explícitamente. Preguntas con alternativas plausibles, exactamente una **mejor respuesta** demostrable según contexto. No incluir dos igualmente correctas.
- Dos convocatorias A/B, con códigos, ventanas de apertura/cierre, autorización por matrícula y banco controlado. No prometer ausencia total de solapamiento si se extraen 200 de 480; planificar pools o etiquetas por convocatoria y comparar equivalencia.

## Multi-universidad
La plataforma atiende varias universidades y materias (ADR-003). SIAF es la primera materia; sus parámetros (4 módulos, 120 por módulo, 200 por intento, 20 s, +1/−1/0, 80 min) son configuración por materia y convocatoria, editable por el docente.

## Flujo alumno
Ingreso con universidad, matrícula y código de convocatoria contra lista autorizada (ADR-004); consentimiento y reglas; iniciar; responder u omitir; progreso y tiempo; cierre; recibo sin clave ni respuestas. Evitar reintentos y reanudaciones fraudulentas. Reanudar solo mismo intento con plazo original, según política configurada.

## Flujo docente
Login con rol, importar banco, revisar y aprobar reactivos, configurar convocatoria, abrir/cerrar, observar estados, exportar resultados CSV (Excel), consultar métricas por módulo y auditoría. Correcciones posteriores de reactivos exigen recálculo versionado y registro de quién autorizó.

## Alcance excluido MVP
Proctoring invasivo, bloqueo absoluto de capturas o IA externa, análisis psicométrico avanzado, calificación con IA en vivo, OCR, acceso anónimo y revelación automática de claves.

## UX
Español, contraste WCAG AA, teclado, diseño escritorio y móvil, aviso claro de reloj, 5 segundos de alerta, confirmación/omisión; ningún cambio de pregunta sin registrar estado. Debe funcionar en conexiones intermitentes con recuperación controlada, sin extender el tiempo.
