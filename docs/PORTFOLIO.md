# InsightHub — AI-Powered Business Analytics Platform

## One Line Summary

I built a full-stack Azure analytics platform that ingests 230,000+ rows of synthetic business data, transforms it through a star-schema SQL pipeline, and surfaces insights through a FastAPI backend, a React dashboard, and a GPT-4o RAG search engine — all deployed and live.

---

## The Problem I Solved

Business intelligence tools like Power BI are powerful but opaque — they hide the data engineering work underneath. I wanted to build something where every layer was visible, debuggable, and something I could talk through in an interview. The goal was to go end-to-end: raw CSVs in blob storage to a production React dashboard with AI-generated insights, with nothing skipped or mocked.

---

## What I Built

- Built a Python ETL pipeline that downloads 7 CSV datasets from Azure Blob Storage, transforms them, and loads 230,000+ rows into a star schema via multi-row SQL INSERT batches
- Designed a star schema in Azure SQL with 6 dimension tables and 3 fact tables, plus a Non-Clustered Columnstore Index on FactSales that cut aggregate query time from ~8 seconds to under 1 second
- Implemented a hybrid RAG search engine using Azure AI Search (BM25 keyword + ada-002 vector embeddings + semantic re-ranking) backed by 20 chunked internal business documents
- Wired GPT-4o as an AI Insights engine that reads live SQL metrics, generates structured JSON findings per business category, and stores them in a dedicated table with idempotent refresh
- Built a FastAPI backend with JWT authentication, role-based access control (Admin / Analyst / Viewer), 14 endpoints, and Application Insights custom event tracking
- Deployed a React 18 + TypeScript frontend with 6 pages (Executive Dashboard, Customer Analytics, Support Operations, Knowledge Search, AI Insights, Login) including a guest demo mode that works offline
- Deployed the backend to Azure App Service (Linux, Python 3.11, B1) and the frontend to Vercel — both live and publicly accessible
- Wrote Bicep IaC for all 13 Azure resources with Key Vault secret references so no password ever appears in plaintext config

---

## Technical Highlights

**Star schema over 3NF normalization** — The dashboard needs to aggregate revenue by product, region, and date simultaneously. A normalized schema would require 4–5 joins per query. The star schema collapses that to 1–2 joins, and the columnstore index makes it fast enough for sub-second dashboard loads on 119,000 FactSales rows.

**Hybrid search beats pure vector search for factual Q&A** — Pure vector search finds semantically similar chunks but misses precise terms. Adding BM25 alongside ada-002 embeddings means the knowledge search handles both "what does the policy say about X?" (semantic) and "what is the exact dollar limit for hotel expenses?" (keyword) correctly. The Azure AI Search semantic re-ranker does a final relevance pass on top.

**GPT-4o in JSON mode with explicit schema** — I used `response_format={"type": "json_object"}` and included an explicit JSON schema in every prompt. This guarantees parseable output and eliminates hallucinated field names. Temperature 0.2 keeps the analysis reproducible across runs.

**Debugging the fast_executemany padding bug** — The `pyodbc` `fast_executemany` mode silently right-pads empty strings with spaces when inserting into fixed-width columns. My geography key lookup was comparing `''` (Python) against `'  '` (SQL), which never matched. I found it by printing raw bytes and fixed it with `.strip()` in the geo map builder. This left ~30,000 FactSales rows with NULL geography keys — re-running the ETL with `--full-reload` closes the gap.

**JWT + RBAC without a framework** — I implemented role-based access control from scratch using FastAPI's dependency injection. Each route declares `Depends(_viewer)`, `Depends(_analyst)`, or `Depends(_admin)` — a single decorator that verifies the JWT and checks the role claim. No external auth library needed; the logic is 40 lines in `deps.py` and fully auditable.

**Startup script strategy for Azure App Service** — Oryx (Azure's build system) kept failing to find `startup.sh` because it generates a wrapper that calls the script without an absolute path. I disabled Oryx entirely (`SCM_DO_BUILD_DURING_DEPLOYMENT=false`), set the startup command to `bash /home/site/wwwroot/startup.sh` with a full path, and run `pip install` inside the startup script with a 30-minute container timeout. Clean and predictable.

**CORS is a silent ERR_NETWORK** — When a browser is blocked by CORS, Axios sees it as `ERR_NETWORK`, not a 4xx response. The frontend showed "Cannot reach the backend" even though the backend was running fine — it was just rejecting the origin header. Adding the frontend domain to `ALLOWED_ORIGINS` and restarting fixed it immediately.

---

## Azure Services Used

| Service | Purpose | Why I chose it |
|---------|---------|----------------|
| Azure SQL Database | Star schema data warehouse (9 tables, 5 views) | SQL Server's columnstore indexes are production-grade for analytics |
| Azure Blob Storage (ADLS Gen2) | Raw CSV landing zone | Native integration with ADF and Python SDK |
| Azure OpenAI (GPT-4o + ada-002) | AI Insights generation + document embeddings | Best-in-class JSON mode and context window for structured analysis |
| Azure AI Search | Hybrid keyword + vector document index | Built-in semantic re-ranking; handles both BM25 and cosine similarity |
| Azure App Service (B1 Linux) | FastAPI backend hosting | Zero-config HTTPS, startup scripts, env var management |
| Azure Key Vault | Secret management for SQL and API keys | Managed Identity integration; no secrets in code or config files |
| Application Insights | Custom event tracking + structured logging | `track_event()` and KQL queries for brute-force detection and latency alerts |
| Azure Bicep | Infrastructure-as-Code for all 13 resources | Declarative, idempotent, integrates with Key Vault secret references |

---

## Results and Metrics

- **230,000+ rows** processed end-to-end through the ETL pipeline (7 CSVs → star schema)
- **119,652 FactSales rows** with columnstore-indexed aggregates running in under 1 second
- **20 business documents** chunked, embedded, and indexed for hybrid RAG search
- **Sub-5-second RAG query response** from question to GPT-4o grounded answer with source citations
- **10 Azure services** integrated in a single working production deployment
- **6 dashboard pages** deployed and publicly accessible
- **14 API endpoints** with JWT auth and three role levels
- **4 AI Insight categories** (Sales, Customers, Support, Campaigns) generated with structured JSON output

---

## Tech Stack

**Data Layer**
- Azure Blob Storage (ADLS Gen2) — raw CSV landing zone
- Python ETL (`pandas`, `pyodbc`, `azure-storage-blob`) — extraction, transformation, multi-row SQL inserts
- Azure SQL Database — star schema (DimDate, DimCustomer, DimProduct, DimEmployee, DimGeography, DimCampaign, FactSales, FactSupportTickets, FactCampaignPerformance)

**Backend Layer**
- FastAPI 0.111 — async API framework, OpenAPI auto-docs
- Pydantic v2 — request/response validation and serialization
- `pyodbc` — SQL Server connectivity with ODBC Driver 17
- `python-jose` + `passlib` — JWT signing and bcrypt password hashing

**AI Layer**
- Azure OpenAI GPT-4o — structured JSON insight generation (temperature 0.2, JSON mode)
- Azure OpenAI text-embedding-ada-002 — 1536-dim document embeddings
- Azure AI Search — HNSW vector index + BM25 + semantic re-ranking
- Custom RAG pipeline — paragraph-aware chunker (300 words, 60-word overlap), hybrid retrieval, grounded answer generation

**Frontend Layer**
- React 18 + TypeScript — component-based UI
- Vite — fast dev server and optimized production build
- Tailwind CSS 3 — utility-first styling
- Recharts — revenue trend lines, campaign ROI bars, segment pie charts
- Axios — typed API client with JWT interceptor and 401 redirect

**Infrastructure Layer**
- Azure App Service (B1 Linux, Python 3.11) — backend hosting
- Vercel — frontend hosting with GitHub integration
- Azure Key Vault — secret management (Key Vault references in App Service)
- Application Insights — telemetry, custom events, KQL alerting
- Bicep IaC — all 13 resources declarative and reproducible

---

## Links

- **Live Demo**: https://insighthub-five.vercel.app
- **GitHub**: https://github.com/PHANI465/insighthub
- **Backend API**: https://insighthub-api-phani.azurewebsites.net
- **API Docs (Swagger)**: https://insighthub-api-phani.azurewebsites.net/docs
