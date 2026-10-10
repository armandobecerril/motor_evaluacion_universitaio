using './main.bicep'

// Producción ISC — evalengine. Sin secretos en este archivo: se leen de variables de entorno
// del operador al momento del despliegue (export EVAL_PG_ADMIN_PASSWORD=..., etc.).

param location = 'southcentralus'
param swaLocation = 'centralus'
param namePrefix = 'isc-evalengine'
param env = 'prod'
param pgAdminLogin = 'evaladmin'

param pgAdminPassword = readEnvironmentVariable('EVAL_PG_ADMIN_PASSWORD')
param appDbPassword = readEnvironmentVariable('EVAL_APP_DB_PASSWORD')
param accessCodePepper = readEnvironmentVariable('EVAL_ACCESS_CODE_PEPPER')

// Fase 1: solo la IP del operador (para migraciones). Fase 2: se agregan las IPs de salida de la API.
param postgresAllowedIps = split(readEnvironmentVariable('EVAL_PG_ALLOWED_IPS', ''), ',')

// Vacío hasta crear el CNAME evalengine.iscit.com.mx → <swaHostname>.
param customDomain = readEnvironmentVariable('EVAL_CUSTOM_DOMAIN', '')

param deployBudget = true
param budgetAmountUsd = 60
param budgetAlertEmail = 'armandobecerril@iscit.com.mx'
