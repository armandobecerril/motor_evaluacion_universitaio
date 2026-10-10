# ADR-005 — Acceso docente con usuario y contraseña

- **Estado:** aceptado (2026-10-10)

## Decisión
Los docentes y administradores entran con **usuario + contraseña** (Entra ID queda como opción futura: `administrators.entra_object_id`).

## Controles
- Hash **Argon2id**; verificación en tiempo constante (también para usuarios inexistentes); mismo mensaje de error para usuario o contraseña incorrectos.
- Bloqueo de cuenta tras 5 fallos (15 min) y límite de 30 intentos por IP cada 15 min (`access_throttle`).
- Sesión opaca en cookie `HttpOnly`, `Secure` (fuera de local), `SameSite=Strict`, `Path=/api`, 8 h; en BD solo el hash (`admin_sessions`). Cambiar la contraseña revoca todas las sesiones.
- CSRF: toda petición que modifica estado exige la cabecera `X-Requested-With: mev` además de SameSite.
- **Contraseña temporal:** el alta con `--temporary` obliga a cambiarla en el primer ingreso; mientras tanto el docente solo puede cambiar su contraseña. Política de contraseña definitiva: ≥ 12 caracteres, 3 tipos de carácter, sin el usuario, no comunes.
- Las contraseñas nunca van en el repositorio, en argumentos de línea de comandos ni en logs: el CLI las lee de `ADMIN_PASSWORD` o por teclado.

## Cuenta inicial
`admin` (platform_admin). En local se puede crear con la contraseña indicada por el operador; en Azure debe crearse con `--temporary` y cambiarse en el primer ingreso.
