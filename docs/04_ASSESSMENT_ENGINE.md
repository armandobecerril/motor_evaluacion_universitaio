# 04 — Reglas del motor de evaluación

## Selección
Usar solo preguntas `approved`, versión congelada por convocatoria. Seleccionar 50 de cada módulo y cuotas de Bloom aproximadas: 15% recordar/comprender, 25% aplicar, 30% analizar, 30% evaluar. Repartir dificultad equitativamente entre convocatorias. No repetir `conceptual_group` si hay cobertura suficiente; si no, abortar con diagnóstico, nunca degradar silenciosamente. Fisher-Yates con RNG seguro para barajar preguntas/opciones; guardar orden para auditoría. Para A/B evaluar pools diferenciados con equivalencia, sin garantizar disjunción total cuando no sea factible.

## Tiempo y concurrencia
La API registra `served_at_utc` y `deadline_utc=served_at+20s` en DB. No confiar en tiempo cliente. Envío de respuesta solo aceptado antes de deadline según tiempo del servidor; tolerancia de red opcional debe definirse y aplicarse uniformemente antes del examen. Cada respuesta usa transacción, idempotencia y comprobación del ordinal; una respuesta tardía se registra como `expired` y no puntúa. No generar preguntas nuevas por refresh; reanudar con deadline original. Si se supera ventana global, cerrar conforme política anunciada.

## Scoring
`correct=+1`, `wrong=-1`, `omitted/expired=0`. `raw=correct-wrong`, `grade=max(0,raw*100/200)`. Validar invariantes `correct+wrong+omitted+expired=200` al finalizar. No calcular nota definitiva en cliente; no permitir resultados negativos. No mostrar claves durante la convocatoria.

## Equidad
La regla de −1 penaliza con fuerza la adivinación; documentarla y someterla a aprobación docente antes de abrir examen. Con cuatro opciones, elegir al azar da esperanza de −0.5 puntos/pregunta. Mantener posibilidad real de omitir y un único mejor distractor no ambiguo. 20 segundos obliga a enunciados cortos; pilotear con estudiantes y ampliar tiempo si las lecturas son injustas.

## Fallos
Ante pérdida de conexión: mostrar estado, reintentar idempotentemente, no reiniciar tiempo. Al recuperar, API devuelve pregunta/estado reales. Ante error servidor: registrar incidencia y permitir resolución administrativa auditada, no manipular notas silenciosamente.
