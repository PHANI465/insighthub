# InsightHub — Power BI Embedded Design

## Status

**Architecturally complete. Activation requires a Power BI Pro or Premium Per User license.**

The backend endpoint, MSAL authentication flow, embed token generation, and frontend component placeholder are all implemented. This document covers the design decisions so the feature can be activated in a single session once a license is available.

---

## Why Power BI Embedded?

The React frontend provides interactive Recharts dashboards for executive KPIs, but Power BI Embedded adds:

- **Self-service analytics**: Business users slice data without engineering support
- **Mobile-optimised reports**: Power BI's responsive layout engine vs. fixed Recharts grids
- **Advanced visuals**: Decomposition tree, key influencers, Q&A natural-language query
- **Scheduled refresh**: Reports auto-refresh from Azure SQL without API calls
- **Export to PDF/Excel**: Built-in report distribution

---

## App-Owns-Data Embedding Architecture

InsightHub uses the **App-Owns-Data** pattern, not User-Owns-Data. This means:

```
                    App-Owns-Data Pattern
                    ─────────────────────

User Browser                                    Microsoft Services
    │                                                    │
    │  1. User logs in (JWT)                            │
    ├──────────────────────────────────────────────────►│
    │                                                    │
    │  2. Frontend requests embed token                 │
    ├─────────────────────────────────────────────────► │
    │              FastAPI Backend                      │
    │                    │                              │
    │                    │  3. MSAL client_credentials  │
    │                    │     flow (service principal) │
    │                    ├──────────────────────────────►
    │                    │                    Azure AD  │
    │                    │◄──────────────────────────── │
    │                    │  4. AAD access token         │
    │                    │                              │
    │                    │  5. POST /GenerateToken      │
    │                    │     Power BI REST API        │
    │                    ├──────────────────────────────►
    │                    │              Power BI Service│
    │                    │◄──────────────────────────── │
    │                    │  6. EmbedToken (short-lived) │
    │                    │                              │
    │◄─────────────────── │                              │
    │  7. {embedToken, embedUrl, reportId}              │
    │                                                    │
    │  8. powerbi.embed(config) via powerbi-client-js   │
    │     Report renders in <div> — no Power BI login   │
    │◄────────────────────────────────────────────────► │
```

**Key difference from User-Owns-Data**: The user never authenticates with Power BI directly. The service principal (Azure AD app registration) owns the Power BI workspace and generates embed tokens on behalf of users. InsightHub's JWT RBAC controls who can request an embed token — Power BI never sees the end user's identity.

### Why App-Owns-Data for InsightHub?

| Consideration | App-Owns-Data | User-Owns-Data |
|--------------|---------------|----------------|
| User needs Power BI account | ❌ No | ✅ Yes (each user) |
| License cost model | One Pro license for the service principal | Pro license per user |
| Control over report access | Application-level RBAC | Power BI workspace roles |
| Row Level Security | Enforced via embed token `identities` | Enforced via user's AAD identity |
| Best for | Internal tools, custom portals | Existing Power BI user base |

InsightHub targets internal users who may not have Power BI accounts — App-Owns-Data is the correct choice.

---

## Backend Implementation (Already Built)

### `backend/app/api/powerbi.py`

```python
GET /api/powerbi/embed-token

# Role required: Admin
# Returns: EmbedTokenResponse(token, embed_url, report_id, expiry)

# Flow:
# 1. get_powerbi_access_token() — MSAL ConfidentialClientApplication
#    using client_id + client_secret from Key Vault
# 2. POST https://api.powerbi.com/v1.0/myorg/groups/{workspace_id}/
#         reports/{report_id}/GenerateToken
# 3. Return embed token valid for 60 minutes
```

### `backend/app/core/config.py` settings

```python
powerbi_client_id:     str = ""   # Azure AD app registration client ID
powerbi_client_secret: str = ""   # from Key Vault: insighthub-powerbi-client-secret
powerbi_tenant_id:     str = ""   # Azure AD tenant ID
powerbi_workspace_id:  str = ""   # Power BI workspace (group) GUID
powerbi_report_id:     str = ""   # Report GUID within the workspace
```

### MSAL Token Acquisition

```python
# auth_service.py pattern (existing)
import msal

app = msal.ConfidentialClientApplication(
    client_id=settings.powerbi_client_id,
    client_credential=settings.powerbi_client_secret,
    authority=f"https://login.microsoftonline.com/{settings.powerbi_tenant_id}",
)

result = app.acquire_token_for_client(
    scopes=["https://analysis.windows.net/powerbi/api/.default"]
)
access_token = result["access_token"]
```

---

## Planned DAX Measures

These measures are designed to match the metrics already surfaced by the FastAPI backend, ensuring parity between the Recharts charts and Power BI visuals.

### Revenue & Sales

```dax
-- Total Revenue (matches /api/metrics/dashboard TotalRevenue)
Total Revenue =
CALCULATE(
    SUMX(FactSales, FactSales[UnitPrice] * FactSales[Quantity] * (1 - FactSales[DiscountPct])),
    FactSales[OrderStatus] IN {"Completed", "Shipped"}
)

-- Gross Profit
Gross Profit =
CALCULATE(
    SUMX(
        FactSales,
        (FactSales[UnitPrice] - FactSales[UnitCost]) * FactSales[Quantity]
            * (1 - FactSales[DiscountPct])
    ),
    FactSales[OrderStatus] IN {"Completed", "Shipped"}
)

-- Gross Margin %
Gross Margin % =
DIVIDE([Gross Profit], [Total Revenue], 0)

-- Month-over-Month Revenue Growth
MoM Revenue Growth % =
VAR CurrentMonth = [Total Revenue]
VAR PriorMonth =
    CALCULATE(
        [Total Revenue],
        DATEADD(DimDate[FullDate], -1, MONTH)
    )
RETURN
    DIVIDE(CurrentMonth - PriorMonth, PriorMonth, BLANK())

-- Average Order Value
Avg Order Value =
DIVIDE([Total Revenue], DISTINCTCOUNT(FactSales[OrderID]), BLANK())
```

### Customer & Churn

```dax
-- Active Customers
Active Customers =
CALCULATE(
    COUNTROWS(DimCustomer),
    DimCustomer[AccountStatus] = "Active"
)

-- Churn Rate %  (matches insights_service.py churn_rate_pct)
Churn Rate % =
VAR Churned =
    CALCULATE(
        COUNTROWS(DimCustomer),
        DimCustomer[AccountStatus] = "Inactive"
    )
VAR Total = COUNTROWS(DimCustomer)
RETURN DIVIDE(Churned, Total, 0)

-- Average Lifetime Value by Segment
Avg LTV =
AVERAGE(DimCustomer[LifetimeValue])

-- New Customers (period-aware)
New Customers =
CALCULATE(
    COUNTROWS(DimCustomer),
    USERELATIONSHIP(DimCustomer[RegistrationDate], DimDate[FullDate])
)
```

### Support Operations

```dax
-- Resolution Rate %  (matches vw_SupportMetrics SLA24h_CompliancePct)
Resolution Rate % =
DIVIDE(
    CALCULATE(COUNTROWS(FactSupportTickets), FactSupportTickets[IsResolved] = TRUE()),
    COUNTROWS(FactSupportTickets),
    0
)

-- Average CSAT  (1–5 scale, matches avg_csat in API)
Avg CSAT =
AVERAGEX(
    FILTER(FactSupportTickets, NOT ISBLANK(FactSupportTickets[SatisfactionRating])),
    FactSupportTickets[SatisfactionRating]
)

-- SLA 24h Compliance %
SLA 24h Compliance % =
DIVIDE(
    CALCULATE(
        COUNTROWS(FactSupportTickets),
        FactSupportTickets[IsResolved] = TRUE(),
        FactSupportTickets[ResolutionHours] <= 24
    ),
    CALCULATE(COUNTROWS(FactSupportTickets), FactSupportTickets[IsResolved] = TRUE()),
    0
)

-- Escalation Rate %
Escalation Rate % =
DIVIDE(
    CALCULATE(COUNTROWS(FactSupportTickets), FactSupportTickets[IsEscalated] = TRUE()),
    COUNTROWS(FactSupportTickets),
    0
)
```

### Campaign ROI

```dax
-- Campaign ROI %  (matches ROI_Pct in vw_CampaignROI)
Campaign ROI % =
DIVIDE(
    SUM(FactCampaignPerformance[RevenueGenerated]) - SUM(FactCampaignPerformance[ActualSpend]),
    SUM(FactCampaignPerformance[ActualSpend]),
    0
) * 100

-- Click-Through Rate %
CTR % =
DIVIDE(
    SUM(FactCampaignPerformance[Clicks]),
    SUM(FactCampaignPerformance[Impressions]),
    0
) * 100

-- Conversion Rate %
Conversion Rate % =
DIVIDE(
    SUM(FactCampaignPerformance[Conversions]),
    SUM(FactCampaignPerformance[Clicks]),
    0
) * 100

-- Budget Utilisation %
Budget Utilisation % =
DIVIDE(
    SUM(FactCampaignPerformance[ActualSpend]),
    SUM(DimCampaign[Budget]),
    0
) * 100
```

---

## Row Level Security Design

RLS restricts what data a user sees within the embedded report — critical if the same report is shown to multiple regional managers or department heads.

### Planned RLS Roles

| RLS Role | Filter Logic | InsightHub Mapping |
|----------|-------------|-------------------|
| `GlobalViewer` | No filter — sees all data | Admin role users |
| `RegionViewer` | `DimGeography[Region] = USERNAME()` | Regional manager — sees only their region |
| `SegmentViewer` | `DimCustomer[CustomerSegment] = USERNAME()` | Segment-specific analyst |

### RLS Implementation in Power BI Desktop

```dax
-- Role: RegionViewer
-- Table: DimGeography
[Region] = USERNAME()

-- USERNAME() returns the value passed in the embed token's
-- identities[].username field, not the user's AAD UPN.
-- This allows application-controlled RLS without AAD identity.
```

### Embed Token with RLS Identity

```python
# In powerbi.py embed token generation:
embed_token_request = {
    "accessLevel": "View",
    "datasetId": "<dataset_guid>",
    "identities": [
        {
            "username": user.username,   # Passed to USERNAME() in DAX
            "roles": ["RegionViewer"],   # Which RLS role to apply
            "datasets": ["<dataset_guid>"]
        }
    ]
}
```

For Admin users, omit the `identities` block entirely — no RLS filter applied.

---

## Embed Token Generation Flow (Detailed)

```
POST /api/powerbi/embed-token
Authorization: Bearer <admin_jwt>

1. FastAPI verifies Admin JWT → proceeds
2. MSAL ConfidentialClientApplication.acquire_token_for_client()
   → POST https://login.microsoftonline.com/{tenant_id}/oauth2/v2.0/token
     client_id={powerbi_client_id}
     client_secret={from Key Vault}
     scope=https://analysis.windows.net/powerbi/api/.default
   ← AAD access token (valid 60 min)

3. Power BI REST API: Generate Embed Token
   → POST https://api.powerbi.com/v1.0/myorg/groups/{workspace_id}/
            reports/{report_id}/GenerateToken
     Authorization: Bearer {aad_access_token}
     Body: {"accessLevel": "View", "identities": [...]}
   ← {"token": "H4sI...", "tokenId": "...", "expiration": "2024-..."}

4. Return to frontend:
   {
     "embed_token": "H4sI...",
     "embed_url": "https://app.powerbi.com/reportEmbed?reportId=...",
     "report_id": "<guid>",
     "expiry": "2024-06-07T10:00:00Z"
   }

5. Frontend (PowerBIReport component):
   import { PowerBIEmbed } from 'powerbi-client-react'

   <PowerBIEmbed
     embedConfig={{
       type: 'report',
       id: reportId,
       embedUrl: embedUrl,
       accessToken: embedToken,
       tokenType: models.TokenType.Embed,
       settings: { panes: { filters: { visible: false } } }
     }}
     cssClassName="powerbi-container"
   />
```

---

## Activation Steps

When a Power BI Pro or Premium Per User license becomes available:

### Step 1 — Create Azure AD App Registration

```bash
# Create app registration
az ad app create \
  --display-name "InsightHub Power BI Embedding" \
  --sign-in-audience AzureADMyOrg

# Note the appId (client_id) from output
CLIENT_ID=<appId from output>

# Create client secret
az ad app credential reset \
  --id $CLIENT_ID \
  --years 2
# Note the password (client_secret) from output — store in Key Vault immediately

# Create service principal
az ad sp create --id $CLIENT_ID
```

### Step 2 — Grant Power BI API Permissions

In the Azure portal → App Registration → API Permissions:
- Add `Power BI Service` → Delegated permissions:
  - `Report.Read.All`
  - `Dataset.Read.All`
  - `Workspace.Read.All`
- Grant admin consent

### Step 3 — Configure Power BI Workspace

In Power BI Service (app.powerbi.com):
1. Create a new workspace: `InsightHub Analytics`
2. Settings → Premium → `Allow service principals to use Power BI APIs`
3. Workspace Access → Add the service principal (`InsightHub Power BI Embedding`) as **Member** or **Contributor**
4. Upload the InsightHub `.pbix` report file to the workspace
5. Note the **Workspace ID** and **Report ID** from the URL:
   `https://app.powerbi.com/groups/{workspace_id}/reports/{report_id}`

### Step 4 — Connect Dataset to Azure SQL

In Power BI Service → Dataset Settings:
- Gateway connection: Azure SQL DirectQuery or scheduled import
- Connection string: `insighthub-sql-phani01.database.windows.net`
- Authentication: Database credentials (or Managed Identity with Premium workspace)

### Step 5 — Add Secrets to Key Vault

```bash
VAULT=insighthub-dev-kv

az keyvault secret set --vault-name $VAULT \
  --name insighthub-powerbi-client-secret --value "<client_secret>"
```

### Step 6 — Set App Service Environment Variables

```bash
az webapp config appsettings set \
  --name insighthub-dev-api \
  --resource-group rg-insighthub-devphani \
  --settings \
    POWERBI_CLIENT_ID="<client_id>" \
    POWERBI_TENANT_ID="<tenant_id>" \
    POWERBI_WORKSPACE_ID="<workspace_guid>" \
    POWERBI_REPORT_ID="<report_guid>"
```

`POWERBI_CLIENT_SECRET` is fetched from Key Vault automatically — do not set it directly.

### Step 7 — Enable Frontend Power BI Route

In `frontend/src/App.tsx`, uncomment the Power BI route (currently commented out with the Phase 5 placeholder).

Install the Power BI client library:
```bash
cd frontend
npm install powerbi-client powerbi-client-react
```

### Step 8 — Verify

```bash
curl -X GET https://insighthub-dev-api.azurewebsites.net/api/powerbi/embed-token \
  -H "Authorization: Bearer <admin_token>"
# Expected: {"embed_token": "H4sI...", "embed_url": "https://app.powerbi.com/...", ...}
```

---

## Frontend Component (Ready to Activate)

```typescript
// frontend/src/pages/PowerBIDashboard.tsx
// Install: npm install powerbi-client powerbi-client-react

import { PowerBIEmbed } from 'powerbi-client-react'
import { models } from 'powerbi-client'
import { useEffect, useState } from 'react'
import client from '../api/client'

interface EmbedConfig {
  embed_token: string
  embed_url: string
  report_id: string
  expiry: string
}

export default function PowerBIDashboard() {
  const [config, setConfig] = useState<EmbedConfig | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    client.get<EmbedConfig>('/api/powerbi/embed-token')
      .then(r => setConfig(r.data))
      .catch(() => setError('Power BI embed token unavailable. Check App Service config.'))
  }, [])

  if (error) return <div className="p-8 text-red-500">{error}</div>
  if (!config) return <div className="p-8">Loading Power BI report...</div>

  return (
    <div className="h-screen w-full">
      <PowerBIEmbed
        embedConfig={{
          type: 'report',
          id: config.report_id,
          embedUrl: config.embed_url,
          accessToken: config.embed_token,
          tokenType: models.TokenType.Embed,
          settings: {
            panes: {
              filters: { visible: false },
              pageNavigation: { visible: true }
            },
            background: models.BackgroundType.Transparent,
          }
        }}
        cssClassName="h-full w-full border-0"
      />
    </div>
  )
}
```

---

## Cost Estimate

| Resource | SKU | Monthly Cost (est.) |
|----------|-----|-------------------|
| Power BI Pro license (1 service principal) | Pro | ~$10/month |
| Power BI Premium Per User (optional, for RLS + larger datasets) | PPU | ~$20/user/month |
| Azure App Service (existing, handles embed token API) | B2 | Already provisioned |

The service principal license is the only additional cost. All Azure infrastructure (SQL, OpenAI, Search) is already provisioned and shared.
