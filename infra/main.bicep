// Motor de Evaluación (ISC) — infraestructura de producción en un grupo de recursos.
// Despliegue (lo ejecuta el operador):
//   az deployment group what-if  -g rg-isc-evalengine-prod -f infra/main.bicep -p infra/prod.bicepparam
//   az deployment group create   -g rg-isc-evalengine-prod -f infra/main.bicep -p infra/prod.bicepparam
// Los secretos se pasan por variables de entorno (ver prod.bicepparam), nunca se guardan en el repo.

targetScope = 'resourceGroup'

@description('Región principal (aprobada: southcentralus).')
param location string = resourceGroup().location

@description('Región de Static Web Apps (servicio global; solo algunas regiones aceptan el recurso).')
@allowed(['centralus', 'eastus2', 'westus2', 'westeurope', 'eastasia'])
param swaLocation string = 'centralus'

@description('Prefijo de nombres. Resultado: psql-<prefix>-<env>, app-<prefix>-api, etc.')
param namePrefix string = 'isc-evalengine'

@allowed(['prod', 'staging'])
param env string = 'prod'

@description('Usuario administrador de PostgreSQL (propietario del esquema; solo migraciones).')
param pgAdminLogin string = 'evaladmin'

@secure()
@description('Contraseña del administrador de PostgreSQL. Solo caracteres URL-safe.')
param pgAdminPassword string

@secure()
@description('Contraseña del rol exam_app (la usa la API). Solo caracteres URL-safe.')
param appDbPassword string

@secure()
@description('Secreto HMAC de los códigos de acceso de examen.')
param accessCodePepper string

@description('IPs públicas autorizadas a PostgreSQL (operador para migraciones y salidas de la App Service).')
param postgresAllowedIps array = []

@description('Dominio personalizado del frontend (vacío = aún no). Requiere el CNAME creado antes.')
param customDomain string = ''

@description('Crear presupuesto mensual con alertas (algunas suscripciones de créditos no lo admiten).')
param deployBudget bool = true
param budgetAmountUsd int = 60
param budgetAlertEmail string = ''
param budgetStartDate string = '2026-10-01'

@description('Etiquetas comunes de los activos de ISC.')
param tags object = {
  owner: 'ISC'
  solution: 'evalengine'
  purpose: 'demo-acelerador-capacitacion-ia'
  environment: env
  managedBy: 'bicep'
}

var suffix = '${namePrefix}-${env}'
var pgName = 'psql-${suffix}'
var dbName = 'evalengine'
var allowedIps = filter(postgresAllowedIps, ip => !empty(trim(ip)))
var kvName = take(replace('kv-${namePrefix}-${uniqueString(resourceGroup().id)}', '--', '-'), 24)

// ------------------------------------------------------------- observabilidad ---

resource logs 'Microsoft.OperationalInsights/workspaces@2023-09-01' = {
  name: 'log-${suffix}'
  location: location
  tags: tags
  properties: {
    sku: { name: 'PerGB2018' }
    retentionInDays: 30
    workspaceCapping: { dailyQuotaGb: json('0.5') }
  }
}

resource appInsights 'Microsoft.Insights/components@2020-02-02' = {
  name: 'appi-${suffix}'
  location: location
  tags: tags
  kind: 'web'
  properties: {
    Application_Type: 'web'
    WorkspaceResourceId: logs.id
    DisableIpMasking: false
  }
}

// ----------------------------------------------------------------- PostgreSQL ---

resource postgres 'Microsoft.DBforPostgreSQL/flexibleServers@2023-12-01-preview' = {
  name: pgName
  location: location
  tags: tags
  sku: { name: 'Standard_B1ms', tier: 'Burstable' }
  properties: {
    version: '17'
    administratorLogin: pgAdminLogin
    administratorLoginPassword: pgAdminPassword
    storage: { storageSizeGB: 32, autoGrow: 'Enabled' }
    backup: { backupRetentionDays: 7, geoRedundantBackup: 'Disabled' }
    highAvailability: { mode: 'Disabled' }
    network: { publicNetworkAccess: 'Enabled' }
    authConfig: { activeDirectoryAuth: 'Disabled', passwordAuth: 'Enabled' }
  }
}

resource database 'Microsoft.DBforPostgreSQL/flexibleServers/databases@2023-12-01-preview' = {
  parent: postgres
  name: dbName
  properties: { charset: 'UTF8', collation: 'en_US.utf8' }
}

resource requireTls 'Microsoft.DBforPostgreSQL/flexibleServers/configurations@2023-12-01-preview' = {
  parent: postgres
  name: 'require_secure_transport'
  properties: { value: 'on', source: 'user-override' }
}

resource minTls 'Microsoft.DBforPostgreSQL/flexibleServers/configurations@2023-12-01-preview' = {
  parent: postgres
  name: 'ssl_min_protocol_version'
  properties: { value: 'TLSv1.2', source: 'user-override' }
  dependsOn: [requireTls]
}

// Sin la regla "permitir todos los servicios de Azure": solo IPs explícitas.
@batchSize(1)
resource pgFirewall 'Microsoft.DBforPostgreSQL/flexibleServers/firewallRules@2023-12-01-preview' = [
  for (ip, i) in allowedIps: {

    parent: postgres
    name: 'allow-${i}'
    properties: { startIpAddress: trim(ip), endIpAddress: trim(ip) }
    dependsOn: [minTls]
  }
]

// ------------------------------------------------------------------ Key Vault ---

resource keyVault 'Microsoft.KeyVault/vaults@2023-07-01' = {
  name: kvName
  location: location
  tags: tags
  properties: {
    tenantId: subscription().tenantId
    sku: { family: 'A', name: 'standard' }
    enableRbacAuthorization: true
    enableSoftDelete: true
    softDeleteRetentionInDays: 7
    publicNetworkAccess: 'Enabled'
  }
}

resource secretDbUrl 'Microsoft.KeyVault/vaults/secrets@2023-07-01' = {
  parent: keyVault
  name: 'database-url'
  properties: {
    value: 'postgresql+psycopg://exam_app:${appDbPassword}@${postgres.properties.fullyQualifiedDomainName}:5432/${dbName}?sslmode=require'
  }
}

resource secretPepper 'Microsoft.KeyVault/vaults/secrets@2023-07-01' = {
  parent: keyVault
  name: 'access-code-pepper'
  properties: { value: accessCodePepper }
}

// --------------------------------------------------------- App Service (API) ---

resource plan 'Microsoft.Web/serverfarms@2023-12-01' = {
  name: 'asp-${suffix}'
  location: location
  tags: tags
  kind: 'linux'
  sku: { name: 'B1', tier: 'Basic' }
  properties: { reserved: true }
}

resource api 'Microsoft.Web/sites@2023-12-01' = {
  name: 'app-${namePrefix}-api'
  location: location
  tags: tags
  kind: 'app,linux'
  identity: { type: 'SystemAssigned' }
  properties: {
    serverFarmId: plan.id
    httpsOnly: true
    clientAffinityEnabled: false
    siteConfig: {
      linuxFxVersion: 'PYTHON|3.12'
      alwaysOn: true
      ftpsState: 'Disabled'
      minTlsVersion: '1.2'
      http20Enabled: true
      healthCheckPath: '/api/health'
      appCommandLine: 'gunicorn -k uvicorn.workers.UvicornWorker -w 2 -b 0.0.0.0:8000 --timeout 60 exam_engine.main:app'
      appSettings: [
        { name: 'APP_ENV', value: env == 'prod' ? 'production' : 'staging' }
        { name: 'WEBSITES_PORT', value: '8000' }
        { name: 'SCM_DO_BUILD_DURING_DEPLOYMENT', value: 'true' }
        { name: 'DATABASE_URL', value: '@Microsoft.KeyVault(SecretUri=${secretDbUrl.properties.secretUri})' }
        { name: 'ACCESS_CODE_PEPPER', value: '@Microsoft.KeyVault(SecretUri=${secretPepper.properties.secretUri})' }
        { name: 'DB_POOL_SIZE', value: '3' }
        { name: 'DB_MAX_OVERFLOW', value: '2' }
        { name: 'APPLICATIONINSIGHTS_CONNECTION_STRING', value: appInsights.properties.ConnectionString }
      ]
    }
  }
}

resource scmBasicAuthOff 'Microsoft.Web/sites/basicPublishingCredentialsPolicies@2023-12-01' = {
  parent: api
  name: 'scm'
  properties: { allow: false }
}

resource ftpBasicAuthOff 'Microsoft.Web/sites/basicPublishingCredentialsPolicies@2023-12-01' = {
  parent: api
  name: 'ftp'
  properties: { allow: false }
}

// La identidad de la API puede leer secretos (rol "Key Vault Secrets User").
resource kvSecretsUser 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  scope: keyVault
  name: guid(keyVault.id, api.id, '4633458b-17de-408a-b874-0445c86b69e6')
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', '4633458b-17de-408a-b874-0445c86b69e6')
    principalId: api.identity.principalId
    principalType: 'ServicePrincipal'
  }
}

// ----------------------------------------------------- Static Web App (frontend) ---

resource swa 'Microsoft.Web/staticSites@2023-12-01' = {
  name: 'swa-${namePrefix}'
  location: swaLocation
  tags: tags
  sku: { name: 'Standard', tier: 'Standard' }
  properties: {
    stagingEnvironmentPolicy: 'Disabled'
    allowConfigFileUpdates: true
  }
}

// Backend vinculado: /api/* del frontend se enruta a la App Service.
resource swaBackend 'Microsoft.Web/staticSites/linkedBackends@2023-12-01' = {
  parent: swa
  name: 'api'
  properties: {
    backendResourceId: api.id
    region: location
  }
}

resource swaDomain 'Microsoft.Web/staticSites/customDomains@2023-12-01' = if (!empty(customDomain)) {
  parent: swa
  name: empty(customDomain) ? 'placeholder' : customDomain
  properties: { validationMethod: 'cname-delegation' }
}

// ------------------------------------------------------------------ Presupuesto ---

resource budget 'Microsoft.Consumption/budgets@2023-11-01' = if (deployBudget && !empty(budgetAlertEmail)) {
  name: 'budget-${suffix}'
  properties: {
    category: 'Cost'
    amount: budgetAmountUsd
    timeGrain: 'Monthly'
    timePeriod: { startDate: budgetStartDate }
    notifications: {
      actual80: {
        enabled: true
        operator: 'GreaterThanOrEqualTo'
        threshold: 80
        contactEmails: [budgetAlertEmail]
        thresholdType: 'Actual'
      }
      forecast100: {
        enabled: true
        operator: 'GreaterThanOrEqualTo'
        threshold: 100
        contactEmails: [budgetAlertEmail]
        thresholdType: 'Forecasted'
      }
    }
  }
}

// ------------------------------------------------------------------- Salidas ---

output apiName string = api.name
output apiHostname string = api.properties.defaultHostName
output apiOutboundIps string = api.properties.possibleOutboundIpAddresses
output swaName string = swa.name
output swaHostname string = swa.properties.defaultHostname
output postgresFqdn string = postgres.properties.fullyQualifiedDomainName
output postgresAdmin string = pgAdminLogin
output databaseName string = dbName
output keyVaultName string = keyVault.name
