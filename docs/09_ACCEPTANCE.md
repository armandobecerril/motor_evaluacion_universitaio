# 09 — Aceptación, hitos y definición de terminado

## Hitos
H0 inventario de archivos, Azure, Git y estimación de costos (sin cambios cloud). **Completado 2026-10-09** (`docs/00_AUDITORIA_H0.md`).
H1 scaffold, migraciones y CI local.
H2 motor seguro con 10 preguntas de demo y tests.
H3 panel docente, importador, reportes y controles.
H4 banco real 480 en lotes, QA y aprobación del profesor.
H5 dos convocatorias configuradas y ensayo end-to-end.
H6 despliegue dev y producción tras autorización explícita.

## Checklist go/no-go
- [ ] Banco de 480 aprobado, 120 por módulo, citas válidas.
- [ ] 200 por intento y 50 por módulo; alternativas reordenadas y auditables.
- [ ] 20 segundos por pregunta, control de servidor, omisión y avance automático.
- [ ] Nota correcta con penalización y cero mínimo.
- [ ] No hay claves en cliente, ni bypass de autorización o reintento.
- [ ] Recuperación de interrupciones definida y probada.
- [ ] Dos convocatorias con políticas y ventanas verificadas.
- [ ] Exportación CSV, pruebas automatizadas y pilotaje docente.
- [ ] Aislamiento entre universidades probado (RLS y autorización API).
- [ ] Prueba de carga con 30 usuarios concurrentes aprobada.
- [ ] Azure coste/tenant/subscription/region aprobados.
- [ ] Backup, monitoreo, rollback y documentación operativa.

## Informe final de Claude
Registrar: commits y SHA, archivos creados, pruebas ejecutadas y resultados, conteo de preguntas por estado, URLs verificadas, recursos/costo estimado, pendientes y riesgos. No presentar tareas incompletas como realizadas.
