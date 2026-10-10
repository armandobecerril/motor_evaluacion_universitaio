# 00 — Auditoría inicial (H0) — 2026-10-09

## Archivos
- Paquete de especificación: `CLAUDE.md`, `README`, `PROMPT_INICIAL_CLAUDE.md`, `docs/01..09`, `bank/` (vacío), `prompts/GENERAR_BANCO_480.md`.
- Fuentes (fuera del repositorio):

| Módulo | PDF | Págs. | Palabras aprox. |
|---|---|---|---|
| M1 | 01_Sistemas-de-Informacion-en-la-Funcion-Financiera.pdf | 15 | 1,680 |
| M2 | 02_Arquitectura-Empresarial.pdf | 23 | 1,500 |
| M3 | 03_El-ERP.pdf | 30 | 2,450 |
| M4 | 04_AUTOMATIZACION-FINANCIERA.pdf | 22 | 2,580 |
| Inspiración | 01_Caso_BMV_MoNeT.pdf | 1 | 530 |
| Inspiración (derechos reservados) | 01_Knight Capital(1).pdf | 11 | 6,700 |

Los cuatro PDF de módulo tienen texto extraíble; no requieren OCR.

## Decisiones del operador
| Tema | Decisión |
|---|---|
| Base de datos | PostgreSQL Flexible Server (ADR-001) |
| Backend | Azure Functions Python 3.12 (ADR-002) |
| Alcance | Multi-universidad y multi-materia; SIAF primero (ADR-003) |
| Acceso alumno | Universidad + matrícula + código de convocatoria (ADR-004, riesgo documentado) |
| Región | South Central US |
| Reglas de examen | Configurables por el docente; por defecto −1 por error, 80 min, 0 s de tolerancia |
| Git / Azure | El operador ejecuta `git push` y `az` manualmente; repositorio `armandobecerril/motor_evaluacion_universitaio` |

## Riesgos
1. **Banco:** M2 (~1,500 palabras) para 120 reactivos implica riesgo de duplicados semánticos. Se hará mapa tema→página y blueprint antes de redactar; si la fuente no soporta 120 distintos, se reporta y se pide decisión.
2. **A/B disjuntas:** factible con 60 + 60 por módulo (cada alumno toma 50 de 60). Requiere ≥ 50 grupos conceptuales por módulo y convocatoria para no repetir grupo.
3. **Conexiones:** B1ms = 35 conexiones de usuario, sin PgBouncer. Pool por instancia 3+2 y máx. 6 instancias; escalar a General Purpose el día del examen.
4. **Cold start:** 1 instancia "always ready" durante la ventana del examen.
5. **Penalización −1:** adivinar al azar tiene esperanza −0.5 por reactivo; requiere aprobación docente y piloto de 20 s.
6. **Identidad:** matrícula + código no verifica identidad (ADR-004).
7. **Herramientas:** el entorno de Claude no tiene `az` ni sesión de GitHub (esperado: el operador los ejecuta). Docker Hub no es accesible desde el entorno de Claude; las pruebas locales usan PostgreSQL 16 y la CI usa PostgreSQL 17.

## Costo estimado (USD/mes, región US, a confirmar en la calculadora de Azure)
| Recurso | Estimado |
|---|---|
| PostgreSQL Flexible B1ms + 32 GiB | ~$12–15 + ~$4 |
| Escalado a D2ds_v5 solo el día del examen | ~$1–3 por examen |
| Static Web Apps Standard | $9 |
| Functions Flex Consumption | ~$0–5 |
| Application Insights, Key Vault, Storage | ~$1–3 |
| **Total producción** | **~$30–40** |

Desarrollo en local (sin costo Azure). El servidor PostgreSQL de producción puede detenerse entre periodos de examen (máximo 7 días por detención).

## Hitos
H0 ✔ · H1 estructura, modelo, migraciones, CI · H2 motor · H3 panel docente · H4 banco por lotes · H5 IaC, carga, guías · H6 despliegue.
