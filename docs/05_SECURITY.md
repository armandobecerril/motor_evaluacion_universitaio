# 05 — Seguridad, privacidad e integridad académica

## Amenazas y controles
- Exposición de respuestas: no incluir `is_correct`, `rationale`, banco completo ni endpoints admin en payloads públicos; probar bundles compilados.
- Manipulación del tiempo/nota: reloj y calificación autoritativos del servidor, snapshots, controles de concurrencia, UTC.
- Suplantación: el operador eligió matrícula + código de convocatoria (ADR-004). No verifica identidad: exigir lista autorizada por convocatoria, token de intento con hash, rate limiting, ventana corta y supervisión. Migrar a SSO o token individual cuando sea posible.
- Fuga entre universidades: RLS FORCE, llaves foráneas compuestas, contexto de tenant por transacción, pruebas de acceso cruzado.
- Duplicados: UNIQUE por usuario/convocatoria, inicio transaccional, idempotencia.
- Abuso: rate limiting, validación Zod, límites de tamaño, logs, alertas, políticas CORS/CSP y HTTPS.
- Roles: docente/admin en Entra ID, autorización API en cada endpoint; nunca confiar solo en rutas ocultas.
- Datos personales: recopilar lo mínimo, aviso de privacidad, retención definida, acceso por necesidad, exportación y borrado conforme normativa aplicable.
- Registro de cambio de pestaña: indicador informativo, no evidencia concluyente de fraude; no prometer bloqueo de IA, dispositivos secundarios ni capturas.
- Dependencias: escaneo de secretos, dependabot/actualizaciones, SAST, backups y recuperación.

## Seguridad de Azure
PostgreSQL Flexible Server con TLS obligatorio; autenticación Entra ID (identidad administrada de la Function App) cuando sea viable, si no contraseña del rol `exam_app` en Key Vault; rol de migraciones separado del rol de la app; Row-Level Security por universidad (ADR-003), roles mínimos, diagnósticos sin PII, alertas de costo, políticas de firewall y control de acceso por ambiente.

## Antes de producción
Threat model revisado, pruebas de autorización cruzada (IDOR), filtración de claves, bypass de deadline, duplicación de intentos, replay de POST, exportación admin no autorizada y restauración de backup.
