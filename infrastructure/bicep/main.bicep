// main.bicep
// Root Bicep template for provisioning all InsightHub Azure resources.
// Orchestrates child modules for:
//   - Azure SQL Server + Database
//   - Azure Data Lake Storage Gen2
//   - Azure Data Factory
//   - Azure AI Search
//   - Azure OpenAI Service
//   - Azure App Service (backend) + Static Web App (frontend)
//   - Key Vault (for secrets)
// Parameters are loaded from a parameters file per environment (dev/staging/prod).
