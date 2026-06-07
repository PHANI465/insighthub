# InsightHub — Security Architecture

## Overview

InsightHub uses a layered defense-in-depth model. Security controls exist at every tier:
network edge → application transport → API authentication → role-based authorization → data access → secrets management → audit logging.

No single compromise point can expose the full system.

---

## Defense in Depth — The Seven Layers

```
┌──────────────────────────────────────────────────────────────────┐
│  Layer 7: Audit & Monitoring (Application Insights)              │
│  All auth events, search queries, insight generation logged       │
├──────────────────────────────────────────────────────────────────┤
│  Layer 6: Secrets Management (Azure Key Vault)                   │
│  No secrets in code, env files, or App Service config            │
├──────────────────────────────────────────────────────────────────┤
│  Layer 5: Data Access (parameterised SQL, least-privilege role)  │
│  pyodbc ? placeholders everywhere; SQL login has no DDL rights   │
├──────────────────────────────────────────────────────────────────┤
│  Layer 4: Role-Based Authorisation (Viewer / Analyst / Admin)    │
│  Every endpoint declares a minimum role via require_role()       │
├──────────────────────────────────────────────────────────────────┤
│  Layer 3: API Authentication (JWT HS256, 60-minute expiry)       │
│  Stateless; bcrypt password verification; timing-safe            │
├──────────────────────────────────────────────────────────────────┤
│  Layer 2: Transport Security (TLS 1.2+, CORS, Trusted Host)      │
│  HTTPS enforced; CORS pinned to known origins; Host header check │
├──────────────────────────────────────────────────────────────────┤
│  Layer 1: Network Perimeter (Azure SQL Firewall, Private DNS)    │
│  SQL Server only reachable from Azure IPs; no public blob access │
└──────────────────────────────────────────────────────────────────┘
```

---

## Azure Key Vault

### Why Key Vault

Secrets stored in `.env` files or App Service Application Settings are readable by anyone with Azure portal access to the resource group. Key Vault separates secrets from application configuration and enforces access through Azure RBAC — the application only gets a secret if its Managed Identity has the `Key Vault Secrets User` role.

### Architecture

```
App Service (Managed Identity) ──RBAC──► Key Vault
         │                                   │
         │  startup: keyvault.py             │  get_secret()
         │  inject_keyvault_secrets_into_env │
         ▼                                   │
    os.environ ◄───────────────────────────┘
         │
    pydantic Settings()
    (reads from os.environ)
```

At startup (`main.py` lifespan), `keyvault.py` calls `inject_keyvault_secrets_into_env()`:

1. Reads `AZURE_KEYVAULT_URL` from the environment (the only non-secret setting)
2. Authenticates via `DefaultAzureCredential` (uses Managed Identity in production)
3. Fetches each secret listed in `_KV_SECRET_MAP`
4. Writes each secret value into `os.environ`
5. `pydantic Settings()` reads the now-populated environment

### Secret Naming Convention

| Key Vault Secret Name            | Environment Variable      | Used By                      |
|----------------------------------|---------------------------|------------------------------|
| `insighthub-db-password`         | `DB_PASSWORD`             | pyodbc connection string     |
| `insighthub-db-user`             | `DB_USER`                 | pyodbc connection string     |
| `insighthub-jwt-secret`          | `JWT_SECRET_KEY`          | HMAC-HS256 token signing     |
| `insighthub-openai-key`          | `AZURE_OPENAI_KEY`        | Azure OpenAI API calls       |
| `insighthub-search-key`          | `AZURE_SEARCH_KEY`        | Azure AI Search API calls    |
| `insighthub-powerbi-client-secret` | `POWERBI_CLIENT_SECRET` | Power BI embed token MSAL    |

### Key Vault Setup Guide

**Step 1 — Create the Key Vault**

```bash
az keyvault create \
  --name insighthub-kv-dev \
  --resource-group rg-insighthub-devphani \
  --location eastus \
  --enable-rbac-authorization true \
  --retention-days 90
```

**Step 2 — Add secrets**

```bash
VAULT=insighthub-kv-dev

az keyvault secret set --vault-name $VAULT \
  --name insighthub-db-password --value "YourSQLPassword"

az keyvault secret set --vault-name $VAULT \
  --name insighthub-db-user --value "insighthub_app"

az keyvault secret set --vault-name $VAULT \
  --name insighthub-jwt-secret --value "$(openssl rand -hex 32)"

az keyvault secret set --vault-name $VAULT \
  --name insighthub-openai-key --value "YOUR_OPENAI_KEY"

az keyvault secret set --vault-name $VAULT \
  --name insighthub-search-key --value "YOUR_SEARCH_KEY"
```

**Step 3 — Grant App Service access (RBAC)**

```bash
# Get App Service managed identity object ID
PRINCIPAL_ID=$(az webapp show \
  --name insighthub-dev-api \
  --resource-group rg-insighthub-devphani \
  --query identity.principalId -o tsv)

# Assign Key Vault Secrets User role
az role assignment create \
  --role "Key Vault Secrets User" \
  --assignee $PRINCIPAL_ID \
  --scope $(az keyvault show --name $VAULT --query id -o tsv)
```

**Step 4 — Configure App Service**

Add one Application Setting in the App Service (not a secret):

```
AZURE_KEYVAULT_URL = https://insighthub-kv-dev.vault.azure.net/
```

All other settings are fetched from Key Vault at runtime — no secrets in App Service config.

### Secret Rotation

1. Update the secret value in Key Vault: `az keyvault secret set --vault-name $VAULT --name <name> --value <new_value>`
2. Restart the App Service: `az webapp restart --name insighthub-dev-api --resource-group rg-insighthub-devphani`
3. The next startup will fetch the new secret. No code change required.

For zero-downtime rotation, Key Vault supports secret versions — run two slot deployments while keeping the old version active.

---

## Managed Identity

### What It Is

A Managed Identity is an Azure AD service principal that Azure creates and manages automatically for a resource (App Service, ADF, VM). The application gets an identity without storing any credentials — Azure rotates the underlying certificate automatically.

InsightHub uses **System-Assigned Managed Identity** on:
- App Service (FastAPI backend) → Key Vault, AI Search, OpenAI, SQL
- Azure Data Factory → Azure Blob Storage (ADLS Gen2)

### Setup Steps for App Service

**Step 1 — Enable Managed Identity**

```bash
az webapp identity assign \
  --name insighthub-dev-api \
  --resource-group rg-insighthub-devphani
```

Or in Bicep:
```bicep
identity: {
  type: 'SystemAssigned'
}
```

**Step 2 — Grant roles**

```bash
PRINCIPAL_ID=$(az webapp show \
  --name insighthub-dev-api \
  --resource-group rg-insighthub-devphani \
  --query identity.principalId -o tsv)

SUBSCRIPTION=$(az account show --query id -o tsv)
RG=rg-insighthub-devphani

# Key Vault Secrets User
az role assignment create \
  --role "Key Vault Secrets User" \
  --assignee $PRINCIPAL_ID \
  --scope "/subscriptions/$SUBSCRIPTION/resourceGroups/$RG/providers/Microsoft.KeyVault/vaults/insighthub-kv-dev"

# Cognitive Services OpenAI User (for Azure OpenAI)
az role assignment create \
  --role "Cognitive Services OpenAI User" \
  --assignee $PRINCIPAL_ID \
  --scope "/subscriptions/$SUBSCRIPTION/resourceGroups/$RG/providers/Microsoft.CognitiveServices/accounts/insighthub-dev-openai"

# Search Index Data Reader (for AI Search reads)
az role assignment create \
  --role "Search Index Data Reader" \
  --assignee $PRINCIPAL_ID \
  --scope "/subscriptions/$SUBSCRIPTION/resourceGroups/$RG/providers/Microsoft.Search/searchServices/insighthub-dev-search"
```

**Step 3 — Remove API keys from config**

Once Managed Identity is in place, remove `AZURE_OPENAI_KEY` and `AZURE_SEARCH_KEY` from Key Vault. Update `config.py` to use `DefaultAzureCredential` for those clients instead of API key auth.

For Azure OpenAI with Managed Identity:
```python
from azure.identity import DefaultAzureCredential, get_bearer_token_provider
from openai import AzureOpenAI

token_provider = get_bearer_token_provider(
    DefaultAzureCredential(),
    "https://cognitiveservices.azure.com/.default"
)

client = AzureOpenAI(
    azure_endpoint=settings.azure_openai_endpoint,
    azure_ad_token_provider=token_provider,
    api_version="2024-02-01",
)
```

### Managed Identity for ADF → Blob Storage

```bash
ADF_PRINCIPAL=$(az datafactory show \
  --factory-name insighthub-dev-adf \
  --resource-group rg-insighthub-devphani \
  --query identity.principalId -o tsv)

az role assignment create \
  --role "Storage Blob Data Contributor" \
  --assignee $ADF_PRINCIPAL \
  --scope "/subscriptions/$SUBSCRIPTION/resourceGroups/$RG/providers/Microsoft.Storage/storageAccounts/insighthubstoragephani01"
```

---

## RBAC Roles

InsightHub defines three application-level roles stored in `dbo.AppUsers.Role`:

### Role Hierarchy

```
Admin ⊃ Analyst ⊃ Viewer
```

Implemented in `backend/app/api/deps.py` via `require_role()` which checks:

```python
ROLE_LEVELS = {"Viewer": 1, "Analyst": 2, "Admin": 3}
ROLE_LEVELS[user.role] >= ROLE_LEVELS[minimum_role]
```

### Role Capabilities

| Capability                            | Viewer | Analyst | Admin |
|---------------------------------------|--------|---------|-------|
| View Executive Dashboard (KPI cards)  | ✅     | ✅      | ✅    |
| View Revenue trend chart              | ✅     | ✅      | ✅    |
| View Campaign ROI chart               | ✅     | ✅      | ✅    |
| View AI Insights                      | ✅     | ✅      | ✅    |
| View Customer segment analytics       | ❌     | ✅      | ✅    |
| View Product performance table        | ❌     | ✅      | ✅    |
| View Support operations metrics       | ❌     | ✅      | ✅    |
| Perform RAG knowledge search          | ❌     | ✅      | ✅    |
| Generate AI Insights (GPT-4o call)    | ❌     | ❌      | ✅    |
| Request Power BI embed tokens         | ❌     | ❌      | ✅    |

### JWT Claims

Each token contains:

```json
{
  "sub": "admin",
  "role": "Admin",
  "user_id": "uuid-here",
  "exp": 1234567890,
  "type": "access"
}
```

Role is embedded in the token — no database lookup on every request. The token is signed with HS256 using `JWT_SECRET_KEY` from Key Vault. Tampering with the role claim invalidates the signature.

### Demo Credentials

| Username | Password                  | Role    |
|----------|---------------------------|---------|
| admin    | `InsightHub@Admin2024!`   | Admin   |
| analyst  | `InsightHub@Analyst2024!` | Analyst |
| viewer   | `InsightHub@Viewer2024!`  | Viewer  |

Passwords are stored as bcrypt hashes (cost factor 12) in `dbo.AppUsers.PasswordHash`.

---

## Transport Security

### TLS

- App Service enforces HTTPS-only (`httpsOnly: true` in Bicep, minimum TLS 1.2)
- `backend/app/main.py` adds `TrustedHostMiddleware` to reject requests with unexpected `Host` headers (prevents host header injection)
- SQL Server connection string includes `Encrypt=yes;TrustServerCertificate=yes`

### CORS

```python
# main.py — CORS is restricted to the frontend origin only
CORSMiddleware(
    allow_origins=settings.get_cors_origins(),  # e.g. http://localhost:3000
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "Accept"],
    max_age=3600,
)
```

`ALLOWED_ORIGINS` in production must be set to the exact Static Web App URL (e.g. `https://insighthub.azurestaticapps.net`).

### Security Headers

For production, add the following via Azure Front Door or a response middleware:

```
Strict-Transport-Security: max-age=31536000; includeSubDomains
X-Content-Type-Options: nosniff
X-Frame-Options: DENY
Content-Security-Policy: default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'
Referrer-Policy: strict-origin-when-cross-origin
```

---

## Application Insights Monitoring

### Tracked Events

| Event Name                   | Trigger                               | Key Properties                                     |
|------------------------------|---------------------------------------|----------------------------------------------------|
| `UserLogin`                  | Successful authentication             | `username`, `role`                                 |
| `UserLoginFailed`            | Failed authentication attempt         | `reason` (no username — avoids enumeration)        |
| `SearchQuery`                | RAG search executed                   | `query_length`, `top_k`, `latency_ms`, `results_count` |
| `InsightGenerationCompleted` | POST /api/insights/generate completes | `triggered_by`, `status`, `generated_count`, `total_tokens` |

### Kusto (KQL) Queries

**Login failure rate by 5-minute window** (brute-force detection):
```kusto
traces
| where customDimensions.event_name == "UserLoginFailed"
| summarize failures=count() by bin(timestamp, 5m)
| where failures > 5
```

**Average search latency by hour**:
```kusto
traces
| where customDimensions.event_name == "SearchQuery"
| project timestamp, latency=tofloat(customDimensions.latency_ms)
| summarize avg_latency=avg(latency) by bin(timestamp, 1h)
```

**Token cost by insight category**:
```kusto
traces
| where customDimensions.event_name == "InsightGenerationCompleted"
| project timestamp, tokens=toint(customDimensions.total_tokens), status=tostring(customDimensions.status)
| summarize total_tokens=sum(tokens) by bin(timestamp, 1d)
```

**All 500 errors by path**:
```kusto
exceptions
| summarize count=count() by outerMessage
| order by count desc
```

---

## Known Security Gaps (Technical Debt)

| Gap | Risk | Remediation |
|-----|------|-------------|
| JWT secret in `.env` (local dev) | Medium | Use Key Vault in production (already supported) |
| SQL firewall allows all Azure IPs | Low | Restrict to App Service outbound IPs via service endpoints |
| API keys in `.env` for AI Search and OpenAI | Medium | Use Managed Identity (code path already exists, needs config) |
| No refresh token rotation | Low | Rotate refresh token on each use (single-use tokens) |
| No rate limiting on `/api/auth/token` | Medium | Add SlowAPI or Azure API Management rate limiting |
| `check_columns.py`, `fix_views.py` at project root have hardcoded credentials | High | Delete these files before any repository sharing |
