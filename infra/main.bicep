// InsightHub — Azure Infrastructure as Code
// Deploys all services needed to run InsightHub end-to-end.
//
// Deploy:
//   az deployment group create \
//     --resource-group rg-insighthub-devphani \
//     --template-file infra/main.bicep \
//     --parameters @infra/parameters.json
//
// Destroy:
//   az group delete --name rg-insighthub-devphani --yes

targetScope = 'resourceGroup'

// ── Parameters ────────────────────────────────────────────────────────────────

@description('Primary Azure region for most resources.')
param location string = resourceGroup().location

@description('Azure region for OpenAI — must support GPT-4o (eastus, westus, swedencentral, etc.).')
param openaiLocation string = 'eastus'

@description('Short environment tag appended to resource names (dev, staging, prod).')
@allowed(['dev', 'staging', 'prod'])
param environment string = 'dev'

@description('SQL Server administrator login name.')
param sqlAdminLogin string

@description('SQL Server administrator password. Must meet Azure complexity rules.')
@secure()
param sqlAdminPassword string

@description('Capacity units for Azure OpenAI GPT-4o deployment.')
param gpt4oCapacity int = 10

@description('Capacity units for text-embedding-ada-002 deployment.')
param embeddingCapacity int = 30

@description('Azure SQL SKU. S2 (50 DTU) for dev; S4/P1 for production analytics workloads.')
@allowed(['S1', 'S2', 'S4', 'P1'])
param sqlSku string = 'S2'

@description('App Service SKU. B2 for dev; P2v3 for production with auto-scale.')
@allowed(['B1', 'B2', 'P1v3', 'P2v3'])
param appServiceSku string = 'B2'

// ── Variables ─────────────────────────────────────────────────────────────────

var prefix = 'insighthub'
var suffix = '${prefix}-${environment}'

// Storage account names must be 3-24 chars, lowercase alphanumeric only
var storageAccountName = take(toLower(replace('${prefix}storage${environment}01', '-', '')), 24)
var sqlServerName      = '${suffix}-sql'
var sqlDatabaseName    = '${prefix}-db'
var keyVaultName       = take('${suffix}-kv', 24)
var appServicePlanName = '${suffix}-plan'
var backendAppName     = '${suffix}-api'
var searchServiceName  = '${suffix}-search'
var openaiAccountName  = '${suffix}-openai'
var appInsightsName    = '${suffix}-appinsights'
var logAnalyticsName   = '${suffix}-logs'
var adfName            = '${suffix}-adf'
var blobContainerName  = 'insighthub'

// ── Log Analytics Workspace ───────────────────────────────────────────────────

resource logAnalytics 'Microsoft.OperationalInsights/workspaces@2023-09-01' = {
  name: logAnalyticsName
  location: location
  properties: {
    sku: {
      name: 'PerGB2018'  // Pay-per-GB; cheapest for dev workloads
    }
    retentionInDays: 30
    publicNetworkAccessForIngestion: 'Enabled'
    publicNetworkAccessForQuery: 'Enabled'
  }
}

// ── Application Insights ──────────────────────────────────────────────────────

resource appInsights 'Microsoft.Insights/components@2020-02-02' = {
  name: appInsightsName
  location: location
  kind: 'web'
  properties: {
    Application_Type: 'web'
    WorkspaceResourceId: logAnalytics.id    // Workspace-based (modern, queryable via KQL)
    IngestionMode: 'LogAnalytics'
    publicNetworkAccessForIngestion: 'Enabled'
    publicNetworkAccessForQuery: 'Enabled'
    RetentionInDays: 30
  }
}

// ── Storage Account (ADLS Gen2) ───────────────────────────────────────────────

resource storageAccount 'Microsoft.Storage/storageAccounts@2023-01-01' = {
  name: storageAccountName
  location: location
  kind: 'StorageV2'
  sku: {
    name: 'Standard_LRS'   // Locally redundant; use ZRS or GRS for production
  }
  properties: {
    isHnsEnabled: true          // Required for ADLS Gen2 (hierarchical namespace)
    minimumTlsVersion: 'TLS1_2'
    allowBlobPublicAccess: false
    supportsHttpsTrafficOnly: true
    accessTier: 'Hot'
    encryption: {
      services: {
        blob: { enabled: true, keyType: 'Account' }
        file: { enabled: true, keyType: 'Account' }
      }
      keySource: 'Microsoft.Storage'
    }
    networkAcls: {
      defaultAction: 'Allow'   // Restrict to VNet in production
      bypass: 'AzureServices'
    }
  }
}

resource blobService 'Microsoft.Storage/storageAccounts/blobServices@2023-01-01' = {
  parent: storageAccount
  name: 'default'
  properties: {
    deleteRetentionPolicy: {
      enabled: true
      days: 7
    }
  }
}

resource container 'Microsoft.Storage/storageAccounts/blobServices/containers@2023-01-01' = {
  parent: blobService
  name: blobContainerName
  properties: {
    publicAccess: 'None'
  }
}

// ── Azure SQL Server ──────────────────────────────────────────────────────────

resource sqlServer 'Microsoft.Sql/servers@2023-05-01-preview' = {
  name: sqlServerName
  location: location
  properties: {
    administratorLogin: sqlAdminLogin
    administratorLoginPassword: sqlAdminPassword
    version: '12.0'
    minimalTlsVersion: '1.2'
    publicNetworkAccess: 'Enabled'
  }
}

// Allow all Azure services (required for App Service → SQL without VNet)
resource sqlFirewallAzure 'Microsoft.Sql/servers/firewallRules@2023-05-01-preview' = {
  parent: sqlServer
  name: 'AllowAllWindowsAzureIps'
  properties: {
    startIpAddress: '0.0.0.0'
    endIpAddress: '0.0.0.0'
  }
}

// Azure SQL Database
resource sqlDatabase 'Microsoft.Sql/servers/databases@2023-05-01-preview' = {
  parent: sqlServer
  name: sqlDatabaseName
  location: location
  sku: {
    name: sqlSku
    tier: startsWith(sqlSku, 'P') ? 'Premium' : 'Standard'
  }
  properties: {
    collation: 'SQL_Latin1_General_CP1_CI_AS'
    maxSizeBytes: 268435456000   // 250 GB limit
    zoneRedundant: false
    readScale: 'Disabled'
    requestedBackupStorageRedundancy: 'Local'
  }
}

// ── Azure Key Vault ───────────────────────────────────────────────────────────

resource keyVault 'Microsoft.KeyVault/vaults@2023-07-01' = {
  name: keyVaultName
  location: location
  properties: {
    tenantId: subscription().tenantId
    sku: {
      family: 'A'
      name: 'standard'
    }
    enableSoftDelete: true
    softDeleteRetentionInDays: 90
    enableRbacAuthorization: true      // Use RBAC not access policies (modern approach)
    enabledForDeployment: false
    enabledForTemplateDeployment: true
    networkAcls: {
      defaultAction: 'Allow'
      bypass: 'AzureServices'
    }
  }
}

// ── App Service Plan ──────────────────────────────────────────────────────────

resource appServicePlan 'Microsoft.Web/serverfarms@2023-01-01' = {
  name: appServicePlanName
  location: location
  sku: {
    name: appServiceSku
    tier: startsWith(appServiceSku, 'B') ? 'Basic' : 'PremiumV3'
  }
  kind: 'linux'
  properties: {
    reserved: true   // Required for Linux
  }
}

// ── FastAPI Backend — App Service ─────────────────────────────────────────────

resource backendApp 'Microsoft.Web/sites@2023-01-01' = {
  name: backendAppName
  location: location
  kind: 'app,linux'
  identity: {
    type: 'SystemAssigned'   // Managed Identity for Key Vault + Azure service access
  }
  properties: {
    serverFarmId: appServicePlan.id
    httpsOnly: true
    siteConfig: {
      linuxFxVersion: 'PYTHON|3.11'
      alwaysOn: appServiceSku != 'B1'   // Keep warm (B1 doesn't support alwaysOn)
      ftpsState: 'Disabled'
      minTlsVersion: '1.2'
      http20Enabled: true
      appCommandLine: 'cd backend && python -m uvicorn app.main:app --host 0.0.0.0 --port 8000'
      appSettings: [
        {
          name: 'AZURE_KEYVAULT_URL'
          value: keyVault.properties.vaultUri
        }
        {
          name: 'APPLICATIONINSIGHTS_CONNECTION_STRING'
          value: appInsights.properties.ConnectionString
        }
        {
          name: 'DB_SERVER'
          value: sqlServer.properties.fullyQualifiedDomainName
        }
        {
          name: 'DB_NAME'
          value: sqlDatabaseName
        }
        {
          name: 'DB_PORT'
          value: '1433'
        }
        {
          name: 'AZURE_SEARCH_ENDPOINT'
          value: 'https://${searchService.name}.search.windows.net'
        }
        {
          name: 'AZURE_SEARCH_INDEX'
          value: 'insighthub-docs'
        }
        {
          name: 'AZURE_OPENAI_ENDPOINT'
          value: openaiAccount.properties.endpoint
        }
        {
          name: 'AZURE_OPENAI_DEPLOYMENT'
          value: 'gpt-4o'
        }
        {
          name: 'AZURE_OPENAI_EMBEDDING_DEPLOYMENT'
          value: 'text-embedding-ada-002'
        }
        {
          name: 'ALLOWED_ORIGINS'
          value: 'https://${backendAppName}.azurewebsites.net'  // Update to Static Web App URL
        }
        {
          name: 'SCM_DO_BUILD_DURING_DEPLOYMENT'
          value: 'true'
        }
        {
          name: 'WEBSITES_PORT'
          value: '8000'
        }
      ]
    }
  }
  dependsOn: [
    searchService
    openaiAccount
    keyVault
    sqlDatabase
  ]
}

// ── Azure AI Search ───────────────────────────────────────────────────────────

resource searchService 'Microsoft.Search/searchServices@2023-11-01' = {
  name: searchServiceName
  location: location
  sku: {
    name: 'basic'   // 1 replica, 1 partition, 15 indexes, 2GB storage per partition
  }
  properties: {
    replicaCount: 1
    partitionCount: 1
    hostingMode: 'default'
    publicNetworkAccess: 'enabled'
    disableLocalAuth: false   // Keep API key auth; switch to managed identity for production
    authOptions: {
      apiKeyOnly: {}
    }
  }
}

// ── Azure OpenAI ──────────────────────────────────────────────────────────────

resource openaiAccount 'Microsoft.CognitiveServices/accounts@2024-04-01-preview' = {
  name: openaiAccountName
  location: openaiLocation
  kind: 'OpenAI'
  sku: {
    name: 'S0'
  }
  properties: {
    publicNetworkAccess: 'Enabled'
    customSubDomainName: openaiAccountName
    networkAcls: {
      defaultAction: 'Allow'
    }
  }
}

// GPT-4o deployment
resource gpt4oDeployment 'Microsoft.CognitiveServices/accounts/deployments@2024-04-01-preview' = {
  parent: openaiAccount
  name: 'gpt-4o'
  sku: {
    name: 'Standard'
    capacity: gpt4oCapacity   // TPM (thousands of tokens per minute)
  }
  properties: {
    model: {
      format: 'OpenAI'
      name: 'gpt-4o'
      version: '2024-05-13'
    }
    versionUpgradeOption: 'OnceNewDefaultVersionAvailable'
  }
}

// text-embedding-ada-002 deployment
resource embeddingDeployment 'Microsoft.CognitiveServices/accounts/deployments@2024-04-01-preview' = {
  parent: openaiAccount
  name: 'text-embedding-ada-002'
  sku: {
    name: 'Standard'
    capacity: embeddingCapacity
  }
  properties: {
    model: {
      format: 'OpenAI'
      name: 'text-embedding-ada-002'
      version: '2'
    }
    versionUpgradeOption: 'OnceNewDefaultVersionAvailable'
  }
  dependsOn: [gpt4oDeployment]  // Deploy sequentially to avoid quota contention
}

// ── Azure Data Factory ────────────────────────────────────────────────────────

resource dataFactory 'Microsoft.DataFactory/factories@2018-06-01' = {
  name: adfName
  location: location
  identity: {
    type: 'SystemAssigned'   // Used to access Blob Storage and SQL
  }
  properties: {
    publicNetworkAccess: 'Enabled'
  }
}

// ── RBAC Role Assignments ─────────────────────────────────────────────────────

// Backend App Service → Key Vault Secrets User
// Allows reading secrets at runtime via DefaultAzureCredential
resource kvBackendRole 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(keyVault.id, backendApp.id, 'Key Vault Secrets User')
  scope: keyVault
  properties: {
    roleDefinitionId: subscriptionResourceId(
      'Microsoft.Authorization/roleDefinitions',
      '4633458b-17de-408a-b874-0445c86b69e6'  // Key Vault Secrets User
    )
    principalId: backendApp.identity.principalId
    principalType: 'ServicePrincipal'
  }
}

// ADF → Storage Blob Data Contributor
// Allows ADF pipelines to read/write the insighthub container
resource adfStorageRole 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(storageAccount.id, dataFactory.id, 'Storage Blob Data Contributor')
  scope: storageAccount
  properties: {
    roleDefinitionId: subscriptionResourceId(
      'Microsoft.Authorization/roleDefinitions',
      'ba92f5b4-2d11-453d-a403-e96b0029c9fe'  // Storage Blob Data Contributor
    )
    principalId: dataFactory.identity.principalId
    principalType: 'ServicePrincipal'
  }
}

// Backend App Service → Search Index Data Reader
// Allows querying the AI Search index without an API key (future Managed Identity auth)
resource searchReaderRole 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(searchService.id, backendApp.id, 'Search Index Data Reader')
  scope: searchService
  properties: {
    roleDefinitionId: subscriptionResourceId(
      'Microsoft.Authorization/roleDefinitions',
      '1407120a-92aa-4202-b7e9-c0e197c71c8f'  // Search Index Data Reader
    )
    principalId: backendApp.identity.principalId
    principalType: 'ServicePrincipal'
  }
}

// Backend App Service → Cognitive Services OpenAI User
// Allows calling OpenAI APIs with Managed Identity (no API key needed)
resource openaiUserRole 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(openaiAccount.id, backendApp.id, 'Cognitive Services OpenAI User')
  scope: openaiAccount
  properties: {
    roleDefinitionId: subscriptionResourceId(
      'Microsoft.Authorization/roleDefinitions',
      '5e0bd9bd-7b93-4f28-af87-19fc36ad61bd'  // Cognitive Services OpenAI User
    )
    principalId: backendApp.identity.principalId
    principalType: 'ServicePrincipal'
  }
}

// ── Outputs ───────────────────────────────────────────────────────────────────

@description('Full URL of the FastAPI backend.')
output backendUrl string = 'https://${backendApp.properties.defaultHostName}'

@description('Azure SQL Server fully qualified domain name.')
output sqlServerFqdn string = sqlServer.properties.fullyQualifiedDomainName

@description('Azure SQL Database name.')
output sqlDatabaseName string = sqlDatabaseName

@description('Key Vault URI — set as AZURE_KEYVAULT_URL environment variable.')
output keyVaultUri string = keyVault.properties.vaultUri

@description('Application Insights connection string — set as APPLICATIONINSIGHTS_CONNECTION_STRING.')
output appInsightsConnectionString string = appInsights.properties.ConnectionString

@description('Azure AI Search endpoint.')
output searchEndpoint string = 'https://${searchService.name}.search.windows.net'

@description('Azure OpenAI endpoint.')
output openaiEndpoint string = openaiAccount.properties.endpoint

@description('Storage account name for ADLS Gen2.')
output storageAccountName string = storageAccount.name

@description('Backend App Service Managed Identity principal ID — needed for RBAC grants.')
output backendPrincipalId string = backendApp.identity.principalId

@description('ADF Managed Identity principal ID — needed for additional RBAC grants.')
output adfPrincipalId string = dataFactory.identity.principalId
