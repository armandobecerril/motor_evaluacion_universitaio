# 06 — Git, Azure y despliegue

## Variables por confirmar ANTES de crear recursos
Tenant, subscription ID, resource group, región (aprobada: South Central US), repositorio GitHub (privado: `armandobecerril/motor_evaluacion_universitaio`), dominio deseado, modalidad de autenticación estudiantil, presupuesto máximo mensual y acceso del operador. Nunca inferir credenciales ni suscripciones de conversaciones previas.

## Flujo recomendado
1. Verificar `node --version`, `az --version`, `az account show`, `gh auth status` SIN imprimir secretos.
2. Preparar monorepo, `.gitignore`, `.env.example`, tests y `infra/main.bicep` parametrizado.
3. Estimar precios de Static Web Apps, Functions (Flex Consumption), Azure Database for PostgreSQL Flexible Server, Insights y tráfico; pedir aprobación. Ver `docs/00_AUDITORIA_H0.md`.
4. Configurar entornos `dev` y `prod`, migraciones idempotentes y seed de prueba solo en dev.
5. Crear workflow de CI: lint, typecheck, unit tests, integración, E2E, revisión de dependencias, validación de Bicep.
6. Configurar CD con permisos mínimos y federación OIDC; requerir aprobación para prod.
7. Desplegar dev, ejecutar smoke tests; desplegar prod solo tras autorización explícita.
8. Documentar URL, SHA, DB migration, configuración de convocatoria, backup y rollback.

## Operación manual
El operador ejecuta personalmente `git push` y todos los comandos `az`; Claude los entrega uno a uno y verifica la salida antes del siguiente.

## PostgreSQL: roles
El administrador de BD crea el rol de la app antes de migrar (ver `apps/api/scripts/bootstrap_roles.sql`). Las migraciones corren con el rol propietario (`MIGRATION_DATABASE_URL`); la API usa `exam_app` (`DATABASE_URL`).

## Comandos orientativos (no ejecutar sin aprobación)
```bash
az login
az account show
az deployment group what-if --resource-group "$RESOURCE_GROUP" --template-file infra/main.bicep --parameters @infra/prod.parameters.json
# Solo después de aprobación explícita:
az deployment group create --resource-group "$RESOURCE_GROUP" --template-file infra/main.bicep --parameters @infra/prod.parameters.json
```

## Rollback
Retener artefacto anterior, ejecutar reversión de frontend/API, mantener compatibilidad de esquema y backups; cambios destructivos requieren aprobación y procedimiento ensayado.
