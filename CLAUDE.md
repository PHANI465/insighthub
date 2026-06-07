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

### Phase 5 — Power BI Embedded ⏳ SKIPPED (no workspace yet)

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

### Phase 8 — React Frontend ⏳ NOT STARTED

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
5. **bcrypt version**: Anaconda environment uses bcrypt 4.0.1 (compatible with passlib 1.7.4). Requirements.txt specifies `passlib[bcrypt]==1.7.4`.

---

## Environment

- Python: Anaconda (`C:\Users\Phaneendra\anaconda3\python.exe`)
- ODBC: ODBC Driver 18 for SQL Server
- All secrets in `.env` at project root
- Azure Key Vault URL configured but SDK not installed in Anaconda env → skipped at startup (expected for local dev)
