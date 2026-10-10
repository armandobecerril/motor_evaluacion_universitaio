# 07 — Plan de pruebas

## Unitarias
- 200 preguntas por intento; exactamente 50 por módulo; no repetidas; semilla/order auditable.
- 4 opciones, exactamente 1 correcta; opciones reordenadas sin alterar clave.
- Scoring: 200 aciertos→100; 100 aciertos/100 errores→0; 150/25/25 omitidas→62.5; 0/200→0; todas omitidas→0.
- Deadlines: 19.999s acepta; 20.001s rechaza; refresh no reinicia; reloj local adulterado irrelevante.
- Respuestas simultáneas/idempotentes no duplican puntuación.

## Integración
- Inicio duplicado bloqueado; expiración y reanudación preservan intento; A/B y cierre de convocatoria; importación transaccional; claves no accesibles a estudiante; admin CSV autorizado; error de DB no corrompe intento.

## Multi-universidad (RLS)
- Sin contexto de universidad no se ve ninguna fila; universidad A no lee ni escribe datos de B; el contexto no se filtra entre transacciones del pool; el rol de la app no es superusuario ni tiene BYPASSRLS.

## Base de datos
- Migraciones reversibles (downgrade/upgrade) y sin diferencias con el modelo (`alembic check`).
- Restricciones: 1 correcta, códigos A–D, aprobación con 4/1 y revisor, inmutabilidad de aprobados, unicidad de intento y de respuesta, append-only, suma de resultados y nota 0–100.

## Carga
- Al menos 30 usuarios concurrentes completando 200 respuestas cada uno contra el ambiente objetivo; p95 de respuesta < 500 ms y 0 errores de conexión.

## E2E
- Alumno completa, omite, expira, recarga, pierde conexión, retoma; docente importa/revisa/aprueba, crea convocatoria, consulta resultados; móvil y teclado.

## Seguridad
- IDOR: alumno A no puede consultar B; docente sin rol no puede acceder; API no expone respuestas, fuentes privadas ni claves; inyección SQL, XSS, CSRF según método de auth; replay y fuerza bruta.

## Banco
- 480 aprobadas (120 por módulo); 200 seleccionables por intento; citas PDF y página válidas; sin duplicados semánticos; distribución de Bloom/dificultad; unívocas; enunciados legibles en 20s; muestra piloto docente.

## Criterio de liberación
Cualquier fallo en scoring, deadline, autenticación, persistencia, aislamiento de claves o calidad del banco BLOQUEA producción.
