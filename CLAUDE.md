# InsightHub — Project Status for Claude

## What This Project Is
End-to-end Azure analytics platform: synthetic data → ADLS Gen2 Blob → Azure Data Factory (or Python ETL) → Azure SQL star schema → FastAPI backend → React frontend.

**Azure SQL database**: `insighthub-db` on `insighthub-sql-phani01.database.windows.net`  
**Blob storage**: `insighthubstoragephani01` container `insighthub`, prefix `raw/insighthub/`

---

## Phase Status

### Phase 1 — Synthetic Data & Blob Upload ✅ COMPLETE
- Synthetic data generated and uploaded to Azure Blob Storage
- Files: `customers.csv` (10K), `products.csv` (500), `employees.csv` (200), `campaigns.csv` (100), `orders.csv` (50K), `order_items.csv` (149K), `support_tickets.csv` (20K)

### Phase 2 — Azure SQL Star Schema ✅ COMPLETE
- Schema deployed: `database/schema/01_dimensions.sql` through `05_views.sql`
- Tables: DimDate (5,113 rows), DimGeography (50K), DimCustomer (10K), DimProduct (500), DimEmployee (200), DimCampaign (100), FactSales (119,652+), FactSupportTickets (20K), FactCampaignPerformance (100)
- Indexes + views deployed. Non-clustered columnstore index on FactSales for analytics queries.
- AppUsers table: deployed (`database/schema/06_app_users.sql`), seeded with 3 demo users via `database/seed_users.py`

### Phase 3 — ETL Pipeline ✅ COMPLETE (with caveats)
**Python-local ETL**: `etl-pipelines/python-local/etl_runner.py`

**Key bugs fixed during Phase 3:**
1. `fast_executemany` type-inference bug (error 8114) → replaced with multi-row `VALUES` inserts in `_bulk_stage()`
2. UUID case mismatch: SQL Server returns uppercase UUIDs, CSV has lowercase → added `.lower()` to key map builders in `loaders.py`
3. `status_y` KeyError in `transform_fact_sales` → fixed to `status` (order_items has no status column, no rename collision)
4. Geography key mismatch: `extract_geographies` normalizes null state → `""` but fast_executemany stored `"  "` (padded) → added `.strip()` to `geo_map` builder AND normalized `_geo_key()` helper in `transform_fact_sales`
5. SatisfactionRating CHECK constraint (must be 1-5 or NULL): `_safe_numeric` was filling NaN with `0` → replaced with `pd.to_numeric(..., errors="coerce")` to preserve NULL
6. `_date_filter()` in metrics_service returned empty string when no dates → fixed to return `WHERE 1=1`

**Outstanding ETL gap**: ~30,195 FactSales rows still have unresolvable GeographyKey. Root cause: DimGeography contains `StateCode = '  '` (two spaces, artifact of the old fast_executemany padding empty strings) but lookup key is `''`. The `geo_map` builder `.strip()` fix resolves this — re-run ETL with `--full-reload` to close the gap.

**Run ETL**: `cd E:\PHANI\Projects\insighthub && python etl-pipelines/python-local/etl_runner.py --full-reload`

### Phase 4 — FastAPI Backend ✅ RUNNING
**Start command (from `backend/`):**
```
cd backend
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```
(Use `python -m uvicorn` — the Anaconda uvicorn.exe is the active one)

**Health check**: `curl http://localhost:8000/api/health` → `{"status":"healthy","database":"connected"}`  
**API docs**: http://localhost:8000/docs

**Config fix**: `backend/app/core/config.py` uses `env_file=("../.env", ".env")` so it finds the project-root `.env` when started from `backend/`.

**Demo credentials** (in AppUsers table):
| Username | Password | Role |
|----------|----------|------|
| admin | InsightHub@Admin2024! | Admin |
| analyst | InsightHub@Analyst2024! | Analyst |
| viewer | InsightHub@Viewer2024! | Viewer |

### Phase 5 — Power BI Embedded ⏳ License required (design complete)

### Phase 6 — Azure AI Search + RAG Pipeline ✅ COMPLETE

**Index name**: `insighthub-docs` on `https://rg-insighthub-devphani.search.windows.net`

**What was built:**
- 20 realistic internal business documents in `ai-search/documents/` (HR, IT, Finance, Sales, Compliance, Operations, Customer Service, Product)
- Azure AI Search index schema: full-text + 1536-dim HNSW vector field + semantic ranking configuration (`insighthub-semantic`)
- Hybrid search (BM25 keyword + cosine vector) with semantic re-ranking fallback
- GPT-4o RAG pipeline with grounded answers and source citations
- FastAPI `/api/search` endpoint wired to the RAG pipeline (requires Analyst role)

**Key files:**
```
ai-search/
├── documents/           # 20 *.md source documents
├── rag-pipeline/
│   ├── config.py        # Settings (reads from .env)
│   ├── chunker.py       # Paragraph-aware word-window chunker (300w, 60w overlap)
│   ├── embeddings.py    # Azure OpenAI embedding client w/ retry
│   ├── indexer.py       # Index creation + document upload
│   ├── searcher.py      # Hybrid search (semantic + vector fallback)
│   ├── rag.py           # Full RAG pipeline (standalone use / testing)
│   └── requirements.txt
└── run_indexer.py       # Entry point: builds the search index
backend/app/services/rag_service.py  # Production RAG service (used by API)
backend/app/api/search.py            # /api/search route (fully wired)
```

**Build the index (run once):**
```
cd E:\PHANI\Projects\insighthub
python ai-search/run_indexer.py
```

**New .env variables added:**
```
AZURE_OPENAI_EMBEDDING_DEPLOYMENT=text-embedding-ada-002
```

**Note:** The embedding model `text-embedding-ada-002` must be deployed in your Azure OpenAI resource. If you used a different deployment name, update `AZURE_OPENAI_EMBEDDING_DEPLOYMENT` in `.env`.

### Phase 7 — AI Insights Engine ✅ COMPLETE

**What was built:**
- `database/schema/07_insights.sql` — `dbo.AIInsights` table with UNIQUEIDENTIFIER PK, indexes
- `backend/app/services/insights_service.py` — full pipeline:
  - `MetricsCollector` — focused SQL queries per category (vw_SalesSummary, DimCustomer, FactSupportTickets, vw_CampaignROI)
  - `InsightGenerator` — GPT-4o with JSON mode, temperature 0.2, category-specific prompts
  - `InsightStore` — idempotent table creation, INSERT, SELECT helpers
  - `run_insight_generation()` — orchestrator; skips existing insights unless force_refresh=True
- `backend/app/api/insights.py` — fully wired (3 endpoints):
  - `GET  /api/insights` — list (Viewer+), category filter, graceful empty before first run
  - `GET  /api/insights/{insight_id}` — full detail with structured_json + metrics_json
  - `POST /api/insights/generate` — Admin only; synchronous; returns created IDs + token usage
- `backend/app/models/schemas.py` — added `InsightDetail`, `GenerateInsightResponse`; fixed `InsightRow.insight_id: str`

**Prompt engineering decisions (8 key choices — see module docstring in insights_service.py):**
1. JSON mode (`response_format=json_object`) — guarantees parseable output
2. Temperature 0.2 — reproducible factual analysis
3. Metrics in user turn, system prompt stable (cacheable)
4. Explicit JSON schema in every prompt — eliminates hallucinated field names
5. Concrete analytical rules per category (e.g. "High if churn > 30%")
6. Period anchoring with exact ISO dates — no vague "recently"
7. Confidence score computed from data completeness, not by GPT-4o
8. max_tokens=1000 per call — prevents truncated JSON

**How to run (first time):**
```
# 1. Generate all 4 insight categories (uses full available data range by default)
curl -X POST http://localhost:8000/api/insights/generate \
  -H "Authorization: Bearer <admin_token>" \
  -H "Content-Type: application/json" \
  -d '{"categories":["Sales","Customers","Support","Campaigns"]}'

# 2. Retrieve insights list
curl http://localhost:8000/api/insights \
  -H "Authorization: Bearer <viewer_token>"

# 3. Get full detail (structured JSON + raw metrics)
curl http://localhost:8000/api/insights/<insight_id> \
  -H "Authorization: Bearer <viewer_token>"
```

### Phase 8 — React Frontend ✅ COMPLETE

**Stack**: React 18 + TypeScript + Vite + Tailwind CSS 3 + Recharts + Axios + React Router v6

**Start command (from `frontend/`):**
```
cd frontend
npm install
npm run dev
```
**Dev URL**: http://localhost:3000 (matches backend CORS `ALLOWED_ORIGINS=http://localhost:3000`)

**Pages:**
| Route | Component | Min Role | Description |
|-------|-----------|----------|-------------|
| `/login` | LoginPage | Public | JWT login form, demo credentials hint |
| `/dashboard` | ExecutiveDashboard | Viewer | 5 KPI cards, Revenue+Profit line chart, Campaign ROI bar |
| `/customers` | CustomerAnalytics | Analyst | Segment table, Revenue bar, Customer distribution pie |
| `/support` | SupportOperations | Analyst | 4 KPI cards, Ticket volume bar, Resolution+CSAT composed chart, detail table |
| `/search` | KnowledgeSearch | Analyst | RAG chat interface, source citation cards, latency display |
| `/insights` | AIInsights | Viewer | Per-category insight cards, expandable key_findings/recommendations (lazy fetch), Generate button (Admin only) |

**Architecture:**
- `src/api/` — axios client with JWT interceptor + 401 redirect; typed wrappers per endpoint
- `src/contexts/AuthContext.tsx` — `useAuth()` hook; role stored in localStorage, RBAC via `hasRole(minRole)`
- `src/components/layout/` — `AppLayout` (Outlet wrapper with role guard), `Sidebar`, `TopBar`
- `src/components/ui/` — `KPICard`, `LoadingSpinner`, `ErrorBanner`, `Badge`
- `src/utils/format.ts` — `formatCurrency`, `formatPct`, `formatInt`, `formatDate`
- `src/types/api.ts` — TypeScript interfaces matching all backend Pydantic schemas

**Key files:**
```
frontend/
├── .env.development          # VITE_API_URL=http://localhost:8000  (dev server)
├── .env.production           # VITE_API_URL=https://insighthub-api.azurewebsites.net  (Vercel build)
├── package.json              # React 18, recharts, lucide-react, axios, react-router-dom
├── vite.config.ts            # port: 3000 (fixed, matches backend CORS)
├── tailwind.config.js
├── src/
│   ├── api/                  # client.ts, auth.ts, metrics.ts, insights.ts, search.ts
│   ├── contexts/             # AuthContext.tsx
│   ├── components/
│   │   ├── layout/           # AppLayout.tsx, Sidebar.tsx, TopBar.tsx
│   │   └── ui/               # KPICard.tsx, LoadingSpinner.tsx, ErrorBanner.tsx, Badge.tsx
│   ├── pages/                # LoginPage, ExecutiveDashboard, CustomerAnalytics,
│   │   │                     # SupportOperations, KnowledgeSearch, AIInsights
│   ├── types/api.ts
│   └── utils/format.ts
```

### Phase 9 — Security & Monitoring ✅ COMPLETE

**Documents created:**
- `docs/security/security-architecture.md` — 7-layer defense-in-depth diagram, Key Vault CLI setup, Managed Identity role assignments, KQL alert queries for brute-force/latency/token cost, security gaps register
- `docs/security/owasp-checklist.md` — All 10 OWASP 2021 categories, every endpoint audited with exact code file references, scorecard table

**Application Insights enhancements (`backend/app/core/appinsights.py` rewritten):**
- Dual-channel: `AzureLogHandler` on `insighthub.events` logger for custom events; root logger handler for WARNING+ exceptions
- `track_event(name, properties)` — writes to App Insights `traces` table, queryable via KQL
- `track_failed_login(reason)` — called on 401; omits username from telemetry (timing-safe, no enumeration)
- `track_metric(name, value, properties)` — numeric telemetry
- `track_exception(exc, properties)` — logs to root logger with full traceback
- All functions wrapped in bare `except: pass` — telemetry never crashes the app

**Bugs fixed in Phase 9:**
1. `sql_campaigns` in `get_kpi_summary()` queried `CampaignStatus` on `FactCampaignPerformance` (column doesn't exist there) → fixed to `FROM dbo.vw_CampaignROI`
2. `/api/metrics/revenue` and `/api/metrics/campaigns` required Analyst but Executive Dashboard is Viewer-accessible → changed both to `Depends(_viewer)`
3. `AS Open` alias in support insight SQL — `OPEN` is reserved in SQL Server (cursor keyword) → renamed to `AS OpenCount`

### Phase 10 — Documentation & IaC ✅ COMPLETE

**Documents created:**
- `docs/architecture/system-design.md` — Mermaid component diagram, star schema rationale, ETL 4-stage architecture, FastAPI DI chain, RAG pipeline flow, React component tree, end-to-end request trace, scaling analysis, technology selection rationale
- `docs/powerbi/powerbi-design.md` — App-Owns-Data vs User-Owns-Data comparison, embed token flow, 12 DAX measures, RLS with USERNAME(), 8-step activation guide, ready-to-use React component
- `docs/interview/interview-qa.md` — 60+ Q&A spanning all 10 phases, each answer grounded in specific codebase decisions
- `docs/screenshots/README.md` — Instructions for capturing 5 feature screenshots

**IaC created:**
- `infra/main.bicep` — 13 Azure resources with `@secure()` parameters, deterministic RBAC `guid()` naming, `dependsOn` for sequential OpenAI deployments
- `infra/parameters.json` — Key Vault `reference` block for `sqlAdminPassword` (never plaintext)

**Backend deployment prep:**
- `backend/startup.sh` — Azure App Service startup script (uvicorn ASGI, 2 workers, proxy-headers)
- `backend/.deployment` — Kudu config pointing to `backend/` subdirectory

**Frontend deployment prep:**
- `frontend/.env.development` — `VITE_API_URL=http://localhost:8000`
- `frontend/.env.production` — `VITE_API_URL=https://insighthub-api.azurewebsites.net`
- `frontend/src/api/client.ts` — updated `VITE_API_BASE_URL` → `VITE_API_URL` (removed TS cast)
- `frontend/vite.config.ts` — `allowedHosts: true` (boolean — string `'all'` does NOT work in Vite)
- Demo banner added to `LoginPage.tsx` — soft blue translucent notice above login card

---

## Deployment Status

| Service | Status | URL |
|---------|--------|-----|
| Frontend | ✅ Live on Vercel | `https://insighthub-five.vercel.app` |
| Backend API | ✅ Live on Azure App Service | `https://insighthub-api-phani.azurewebsites.net` |
| Azure SQL Database | ✅ Active | `insighthub-sql-phani01.database.windows.net` |
| Azure AI Search | ✅ Active | `rg-insighthub-devphani.search.windows.net` |
| Azure OpenAI | ✅ Active | gpt-4o + text-embedding-ada-002 deployed |
| Application Insights | ✅ Active | Custom events wired in backend |

**Backend deploy command (to redeploy):**
```bash
# Build zip with Python (preserves forward-slash paths for Linux rsync)
python -c "
import zipfile, os
src_dir = 'backend'
out_zip = 'insighthub-backend.zip'
exclude_dirs = {'__pycache__', '.git'}
exclude_ext = {'.pyc', '.pyo', '.env'}
os.remove(out_zip) if os.path.exists(out_zip) else None
with zipfile.ZipFile(out_zip, 'w', zipfile.ZIP_DEFLATED) as zf:
    for root, dirs, files in os.walk(src_dir):
        dirs[:] = [d for d in dirs if d not in exclude_dirs]
        for f in files:
            if not any(f.endswith(e) for e in exclude_ext) and f != '.env':
                fp = os.path.join(root, f)
                zf.write(fp, os.path.relpath(fp, src_dir).replace(os.sep, '/'))
"
az webapp deploy --name insighthub-api-phani --resource-group rg-insighthub-dev \
  --src-path insighthub-backend.zip --type zip
```

---

## File Structure

```
insighthub/
├── .env                              # All secrets (never commit!)
├── CLAUDE.md                         # This file
├── backend/
│   ├── app/
│   │   ├── api/       auth.py, metrics.py, search.py, insights.py, powerbi.py
│   │   ├── core/      config.py, database.py, security.py, appinsights.py, keyvault.py
│   │   ├── models/    schemas.py
│   │   └── services/  auth_service.py, metrics_service.py, insights_service.py, rag_service.py
│   └── requirements.txt
├── database/
│   ├── schema/        01-07 SQL files  (07_insights.sql = AIInsights table)
│   └── seed_users.py
├── frontend/
│   ├── .env.development  VITE_API_URL=http://localhost:8000
│   ├── .env.production   VITE_API_URL=https://insighthub-api-phani.azurewebsites.net
│   ├── package.json  React 18 + TypeScript + Vite + Tailwind + Recharts
│   ├── src/          Full TypeScript source (28 files)
│   └── index.html
├── docs/
│   ├── security/     security-architecture.md, owasp-checklist.md
│   ├── architecture/ system-design.md
│   ├── powerbi/      powerbi-design.md
│   ├── interview/    interview-qa.md
│   └── screenshots/  README.md (capture instructions for 5 PNGs)
├── infra/
│   ├── main.bicep    All 13 Azure resources as code
│   └── parameters.json  Key Vault reference for sqlAdminPassword
└── etl-pipelines/python-local/
    ├── etl_runner.py  main orchestrator
    ├── loaders.py     DB staging + MERGE
    ├── transformers.py data transformations
    ├── validators.py  input validation
    ├── blob_reader.py Azure Blob download
    ├── watermark.py   incremental load tracking
    ├── config.py      ETL settings
    └── db_connection.py
```

---

## Git Commit Rules

- **Never add `Co-Authored-By: Claude` lines** to any commit message.
- All commits must show only **Phani465** as the author.
- Commit messages should be concise and describe the "why", not just the "what".

---

## Known Issues / Technical Debt

1. **FactSales 30K gap**: ~20% of rows have international shipping addresses where `StateCode` was padded with spaces by the old ETL. Fixed in code (`.strip()` in geo_map builder), needs one `--full-reload` re-run to apply.
2. **ETL speed**: Multi-row VALUES inserts are functional but slow (~2-3 hours for full reload due to Azure SQL latency + 9-index FactSales table). Consider BULK INSERT or disabling NCCI during load for production.
3. **`test_conn.py`** at project root: diagnostic script, should be deleted before merge.
4. **`check_columns.py`** and **`fix_views.py`** at project root: contain hardcoded credentials, should be deleted.
5. **bcrypt version**: requirements.txt now pins `bcrypt==3.2.2`. passlib 1.7.4's `detect_wrap_bug()` uses a >72-byte test password which causes a `ValueError` in bcrypt 4.x (Rust rewrite enforces 72-byte limit). bcrypt 3.x (Python impl) doesn't have this restriction.
6. **ALLOWED_ORIGINS**: Set to `http://localhost:3000,https://insighthub-five.vercel.app,https://frontend-xi-sandy-95.vercel.app`. Add new deployment URLs after each `vercel deploy --prod`.

---

## Azure App Service Deployment Notes

**App name**: `insighthub-api-phani`  
**Resource group**: `rg-insighthub-dev`  
**Region**: Central US (East US/East US 2/West US 2 had quota=0 on the free trial)  
**SKU**: B1 Linux, Python 3.11  
**Startup**: `bash /home/site/wwwroot/startup.sh` (absolute path required — Oryx wrapper can't find it via PATH)  
**Build**: `SCM_DO_BUILD_DURING_DEPLOYMENT=false` — Oryx disabled. startup.sh runs `pip install` at container start (~2 min).  
**Timeout**: `WEBSITES_CONTAINER_START_TIME_LIMIT=1800` (30 min — pip install is ~2 min actual)  
**Key settings set**: DB_SERVER, DB_NAME, DB_USER, DB_PASSWORD, AZURE_SEARCH_ENDPOINT, AZURE_SEARCH_KEY, AZURE_OPENAI_ENDPOINT, AZURE_OPENAI_KEY, JWT_SECRET_KEY, ALLOWED_ORIGINS, APPLICATIONINSIGHTS_CONNECTION_STRING  
**SQL Firewall**: `AllowAzureServices` rule added (0.0.0.0/0.0.0.0)

## Environment

- Python: Anaconda (`C:\Users\Phaneendra\anaconda3\python.exe`)
- ODBC: ODBC Driver 18 for SQL Server (local); Driver 17 in App Service (pre-installed)
- All secrets in `.env` at project root
- Azure Key Vault URL configured but SDK not installed in Anaconda env → skipped at startup (expected for local dev)
