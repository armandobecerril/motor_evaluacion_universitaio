# PROMPT INICIAL PARA CLAUDE CODE

> Nota (2026-10-09): el stack fue actualizado por `docs/adr/ADR-001..004`: PostgreSQL en lugar de Azure SQL, API en Python Functions, plataforma multi-universidad y acceso por matrícula + código. Donde este texto difiera, prevalecen los ADR.

Quiero que implementes este repositorio como una plataforma web de examen MBA de Sistemas Informáticos Aplicados a Finanzas, lista para operar en Azure. Lee primero `CLAUDE.md` y todos los documentos de `docs/`; utiliza los seis PDF de `source_materials/` como material académico. No te limites a explicar: crea código, migraciones, pruebas, scripts, documentación y commits versionados.

**Primero**: audita entorno y archivos, presenta plan por hitos, riesgos, estimación de costo Azure y decisiones que necesitan autorización. No crees recursos, no hagas push, ni despliegues sin mi aprobación explícita.

**Después de aprobar el plan**: construye frontend React/Vite/TS, backend Azure Functions Python + PostgreSQL (ADR-001/002), IaC Bicep, CI/CD GitHub Actions (preferir OIDC/federación sobre secretos persistentes), panel docente, importador de banco, motor de examen, dos convocatorias, scoring +1/−1/0, temporizador 20 segundos y exportación CSV compatible con Excel. Implementa controles de seguridad y pruebas automatizadas descritas en los documentos.

**Banco académico obligatorio**: produce un archivo de 480 preguntas reales en `bank/questions.review.json` con 120 por módulo, fundamentadas en las cuatro presentaciones, con fuente y página. Los dos casos adicionales sirven SOLO para construir escenarios ficticios, no preguntas factuales sobre ellos. No inventes referencias ni rellenes cantidades artificialmente. Trabaja en lotes revisables de 30–40 reactivos, valida cada lote y marca `draft`; entrega también un reporte de duplicados, ambigüedad, cobertura, distribución de respuestas y Bloom. No promociones a `approved` sin revisión docente. Si el contexto o el tiempo no permiten generar 480 válidas, deja constancia del número real y continúa por lotes en la siguiente ejecución.

**Diseño**: español, MBA, accesible y sobrio, azul marino/blanco/gris; preguntas breves que puedan leerse y resolverse en 20 segundos, escenarios de negocio, no programación. Selección de 200 preguntas (50 por módulo) con equivalencia de dificultad; versiones A y B, cada alumno recibe un orden distinto y no puede reintentar sin autorización. Mostrar opción de omitir; al expirar se omite y avanza. Calificación final max(0,(correctas−incorrectas)/200*100). No revelar respuestas durante el examen.

**Entregables**: código ejecutable, README con comandos exactos, `.env.example`, SQL migrations, seed seguro de muestra (NO el banco completo en frontend), JSON del banco y Excel/CSV de revisión, tests, Bicep, workflows, reporte de despliegue y guía de operación/rollback. Confirma qué has hecho realmente y qué queda pendiente.
