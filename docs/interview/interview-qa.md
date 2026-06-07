# InsightHub — Interview Q&A

Covers every phase of the InsightHub project. Each answer is grounded in specific implementation decisions made in this codebase.

---

## Phase 1 — Synthetic Data & Azure Blob Storage

**Q: Why did you generate synthetic data instead of using a public dataset?**

A: Synthetic data gave me full control over the schema. I needed specific relationships — customers with orders, orders with line items, campaigns that link to geographies — to build a realistic star schema. Public datasets rarely have the right cardinality or join keys. I generated 10K customers, 500 products, 50K orders, 149K order line items, 20K support tickets, and 100 campaigns, all with referential integrity, so the ETL and analytics layers had meaningful data to work with.

**Q: What is ADLS Gen2 and how does it differ from regular Azure Blob Storage?**

A: ADLS Gen2 is Azure Blob Storage with the hierarchical namespace (HNS) feature enabled. HNS adds true directory semantics — rename and delete are O(1) operations on a directory rather than O(n) operations that touch every file. This matters for Spark and ADF workloads that use directory partitioning (e.g. `raw/insighthub/year=2024/month=01/`). Regular Blob Storage uses a flat namespace where "folders" are just key prefixes. I enabled HNS on the storage account in Bicep with `isHnsEnabled: true`.

**Q: How did you structure the files in Blob Storage?**

A: Files live under the prefix `raw/insighthub/` in the `insighthub` container: `raw/insighthub/customers.csv`, `raw/insighthub/orders.csv`, etc. This prefix structure makes it easy to add partitioned data later (e.g. `raw/insighthub/orders/year=2024/month=01/*.csv`) without changing the downstream ETL pipeline path logic.

**Q: What security controls exist on the storage account?**

A: Three controls: (1) `allowBlobPublicAccess: false` — no anonymous reads; (2) `supportsHttpsTrafficOnly: true` — HTTP connections rejected; (3) `minimumTlsVersion: TLS1_2` — older TLS versions refused. In production I would add a private endpoint so Blob Storage is only accessible from within the VNet, removing it from the public internet entirely.

---

## Phase 2 — Azure SQL Star Schema

**Q: Why a star schema instead of a normalised 3NF schema?**

A: Analytical queries need to aggregate millions of rows across multiple dimensions — revenue by product category by month by geography. In 3NF, this requires many joins through a chain of bridge tables, which the query optimizer struggles with at scale. A star schema has only one join per dimension table, and the denormalised structure means the optimizer can use hash joins efficiently. The non-clustered columnstore index on FactSales compresses the numeric columns 5–10× and enables batch-mode execution, which can be 100× faster than row-mode for aggregation queries.

**Q: Why is DimDate.DateKey an INT (YYYYMMDD) instead of a DATE type?**

A: This is industry standard for data warehouses. INT comparisons are faster than DATE comparisons because the CPU can use integer arithmetic directly. YYYYMMDD format preserves natural ordering — `20240115 < 20240116` is the correct chronological order as an integer. You can also do arithmetic directly: `WHERE DateKey BETWEEN 20240101 AND 20241231` instead of casting. Every fact table row stores a DateKey as INT, making the join on a fixed-width integer type rather than a variable-length DATE type.

**Q: What is a non-clustered columnstore index and why did you put it on FactSales?**

A: A columnstore index stores data column-by-column rather than row-by-row. For analytics queries that read a few columns from millions of rows (e.g. `SUM(GrossRevenue)`, `COUNT(DISTINCT CustomerKey)`), this is far more efficient because only the needed columns are loaded from disk, and the columnar format compresses well. Batch-mode execution processes 900 rows at a time in a vectorized fashion. The trade-off is that INSERT/UPDATE are slower because the delta store is maintained, but FactSales is append-heavy, so this is acceptable.

**Q: How did you handle the DimDate table — did you generate it manually?**

A: Yes. I generated 5,113 date rows spanning the full data range (2022–2035) with derived columns: `CalendarYear`, `MonthNumber`, `MonthYear` (e.g. "Jan 2024"), `QuarterLabel` (e.g. "Q1"), `WeekOfYear`, `DayOfWeek`, `IsWeekend`, `IsHoliday`. These derived columns make reporting queries dramatically simpler — instead of `DATEPART(quarter, OrderDate)`, you join to DimDate and read `QuarterLabel` directly.

**Q: What are the reporting views and why use views instead of querying base tables?**

A: Four views: `vw_SalesSummary`, `vw_CampaignROI`, `vw_SupportMetrics`, `vw_ProductPerformance`. Views serve two purposes: (1) they encapsulate complex multi-table JOINs so the API service layer writes simple `SELECT ... FROM dbo.vw_SalesSummary` queries instead of 6-table JOINs; (2) they decouple the API contract from the physical schema — if I rename a column in FactSales, I update the view definition and the API stays unchanged.

---

## Phase 3 — ETL Pipeline

**Q: Explain the ETL architecture — blob_reader, validators, transformers, loaders.**

A: Four-stage pipeline: `blob_reader.py` downloads CSVs from Azure Blob using `BlobServiceClient` and returns a pandas DataFrame. `validators.py` enforces schema — checks required columns exist, coerces types, handles nulls, validates value ranges (e.g. SatisfactionRating must be 1–5). `transformers.py` performs key lookups — for example, `transform_fact_sales` looks up CustomerKey by email, ProductKey by product ID, DateKey by order date, and GeographyKey by city+state+country, building the foreign keys for the fact table. `loaders.py` writes to Azure SQL using MERGE for dimension tables (idempotent) and multi-row VALUES inserts for fact tables.

**Q: What is the watermark pattern and why do you need it?**

A: The watermark stores the timestamp of the last successful ETL load per entity in a control table. On the next run, we only process records modified after that timestamp — `WHERE modified_date > ?`. This avoids re-processing 149K order line items on every daily run. The `--full-reload` flag bypasses the watermark and reloads everything from scratch. The incremental pattern requires a reliable `modified_date` column on the source data; synthetic data has this because each record has a `created_at` timestamp.

**Q: You fixed six ETL bugs. Walk me through the most complex one.**

A: The geography key mismatch was the hardest to diagnose. The symptom was ~30K FactSales rows with `GeographyKey = NULL`. The root cause involved two separate bugs compounding each other: first, when the old ETL used `fast_executemany`, SQL Server's ODBC driver padded empty strings with spaces — so a city with no state stored `'  '` (two spaces) in `DimGeography.StateCode`. Second, the lookup key builder in `transformers.py` was using the raw value without stripping whitespace. So the lookup tried to match `''` against `'  '` and missed. The fix was `.strip()` in both places — on the stored geography dimension and on the lookup key construction. The fix also required a `--full-reload` to clean the padded rows already in DimGeography.

**Q: Why did you replace fast_executemany with multi-row VALUES inserts?**

A: `pyodbc.fast_executemany` infers data types from the first row of the batch. If the first row has a NULL in a column, pyodbc infers the column type as NULL-compatible, but if a later row has a non-NULL value of an unexpected type, SQL Server raises Error 8114 (data type conversion error). Multi-row VALUES inserts send a single parameterised INSERT statement with all rows as parameter sets — SQL Server infers types from the declared column types in the table definition, not from the first row's runtime value.

**Q: Why did FactCampaignPerformance end up empty after multiple ETL runs?**

A: The `etl_runner.py` has an `--entity` argument to filter which entities to load, but the argument parsing code existed without actually being applied to filter the execution flow. Combined with the watermark pattern, which skips entities where the watermark timestamp is already beyond the source data's modification dates, all 100 campaigns were always skipped on incremental runs. I solved it by writing `load_campaigns_only.py` — a targeted script that truncates and reloads just FactCampaignPerformance from the 100 campaign rows in under 3 seconds.

---

## Phase 4 — FastAPI Backend

**Q: Why FastAPI over Flask or Django?**

A: Three reasons: (1) FastAPI generates an OpenAPI/Swagger spec automatically from the function signatures and Pydantic models — no separate docs to maintain. (2) Pydantic validates every request body and response automatically — I define `LoginRequest` with a username and password field and FastAPI rejects malformed requests before my code runs. (3) FastAPI is built on Starlette which is async-capable — for IO-bound operations like database calls, this matters for throughput. Flask requires explicit async extensions and Django is too heavy for an API-only service.

**Q: How does JWT authentication work in this project?**

A: On login, `auth_service.authenticate_user()` queries `dbo.AppUsers` for the username, then calls `passlib.bcrypt.verify(plain_password, stored_hash)` — constant-time comparison that prevents timing attacks. On success, `security.create_access_token()` creates an HS256 JWT with claims: `sub` (username), `role`, `user_id`, `exp` (60 minutes), `type: access`. Every subsequent request includes `Authorization: Bearer <token>`. The `get_current_user()` FastAPI dependency decodes and validates the token on each request — no database hit needed because all claims are in the signed token.

**Q: How does the RBAC system work?**

A: Three roles with a numeric hierarchy: Viewer=1, Analyst=2, Admin=3. `require_role("Analyst")` in `deps.py` checks `ROLE_LEVELS[user.role] >= ROLE_LEVELS["Analyst"]`. This is added as a FastAPI `Depends()` parameter on each endpoint function — FastAPI calls it automatically before the handler runs and raises 403 if the check fails. The role is embedded in the JWT claim so there's no database lookup per request — the signed token proves the role was assigned at login time.

**Q: What is the dependency injection pattern used in FastAPI, and how does InsightHub use it?**

A: FastAPI's `Depends()` is a dependency injection system where you declare what a function needs and FastAPI resolves it. InsightHub chains three dependencies: `get_db_conn()` creates a pyodbc connection and closes it after the request; `get_current_user(conn=Depends(get_db_conn))` decodes the JWT and returns a `UserInfo`; `require_role("Analyst")(user=Depends(get_current_user))` checks the role. Each endpoint declares exactly what it needs: `def get_customers(conn=Depends(get_db_conn), _user=Depends(_analyst))`. FastAPI composes the chain, handles errors at any step, and ensures the DB connection is always closed.

**Q: Why use pyodbc directly instead of SQLAlchemy ORM?**

A: This is an analytics API, not a CRUD API. The queries are complex analytical SQL against reporting views — joins across 6 tables, window functions, columnstore-optimized aggregations. An ORM adds an abstraction layer optimized for entity CRUD operations, not analytical aggregations. Writing `SUM(GrossRevenue)` in SQLAlchemy requires understanding its Core expression language, which adds complexity without benefit here. Raw parameterised pyodbc queries are simpler to write, easier to debug, and have less overhead. The key safety requirement — preventing SQL injection — is fully satisfied by `?` placeholders.

---

## Phase 6 — Azure AI Search + RAG Pipeline

**Q: What is hybrid search and why is it better than pure vector search?**

A: Hybrid search combines BM25 keyword search (TF-IDF based relevance score) with cosine similarity vector search in a single query. BM25 excels at exact term matches — if someone searches "ISO-27001 compliance", BM25 finds documents containing those exact tokens. Vector search excels at semantic similarity — "what are our vacation policies" finds "annual leave entitlement" documents even without exact keyword overlap. By combining both with equal weights (0.5 each in Azure AI Search's `vector_queries` + `search_text`), you get results that are both semantically relevant and lexically precise. Pure vector search misses rare proper nouns; pure keyword search misses paraphrased intent.

**Q: What is semantic re-ranking and when does it help?**

A: After BM25 + vector retrieval returns the top-50 candidate documents, semantic re-ranking runs a cross-encoder transformer over (query, document) pairs to produce a more nuanced relevance score. The cross-encoder sees the query and the full document chunk together — it can understand that "Q3 budget approval process" is more relevant to "quarterly financial planning" than to "budget template download" even if both contain "budget". This adds ~200ms latency but significantly improves precision. It's enabled via `query_type="semantic"` and the named semantic configuration `insighthub-semantic` registered on the index.

**Q: How does your chunking strategy work?**

A: `chunker.py` uses a paragraph-aware word-window approach. It splits each document on blank lines into paragraphs, then builds 300-word chunks with 60-word overlaps. Paragraph awareness means a chunk never cuts in the middle of a logical paragraph — the overlap ensures that sentences near a chunk boundary appear in both adjacent chunks so questions spanning the boundary still find relevant context. Each chunk becomes one index document with its parent document's title and category, so the source citation in the UI shows meaningful provenance.

**Q: How does the RAG pipeline avoid hallucination?**

A: Three mechanisms: (1) The system prompt says "Base ALL analysis strictly on the metrics supplied. Never invent numbers, trends, or facts not present in the data." GPT-4o follows system prompt constraints reliably when they're explicit rules, not vague suggestions. (2) The retrieved context chunks are passed verbatim — GPT-4o is grounding its answer in the actual document text. (3) Source citations are returned alongside the answer — if GPT-4o claims something not in any source, the absence of a citation makes it auditable. For the knowledge search, if no relevant chunks are retrieved (score below threshold), the pipeline returns "I couldn't find relevant information" rather than generating an answer from training data.

**Q: What is the 1536-dimension HNSW vector index?**

A: `text-embedding-ada-002` produces 1536-dimensional float vectors representing the semantic content of each chunk. HNSW (Hierarchical Navigable Small World) is a graph-based approximate nearest neighbour algorithm. It builds a multi-layer graph where each node is connected to its most similar neighbours. At query time, it navigates the graph starting from random entry points, following edges toward the nearest neighbours in O(log n) time rather than O(n) linear scan. `ef=500` controls the search depth — higher values mean more accurate results at the cost of more computation. Azure AI Search stores and queries the HNSW index as a first-class index field type (`Collection(Edm.Single)` with `dimensions: 1536`).

---

## Phase 7 — AI Insights Engine

**Q: Walk me through the full insight generation pipeline.**

A: Four stages per category: (1) `MetricsCollector` runs focused SQL queries against the reporting views — for Sales, it queries revenue by month, top product categories, period-over-period growth, and prior-period comparison. The SQL is designed to return only the metrics needed for that category to keep the prompt token count small. (2) `InsightGenerator._call()` sends a GPT-4o request with `response_format=json_object` — this forces the model to return only valid JSON with no markdown wrapping. The system prompt establishes the analyst persona with explicit rules; the user turn contains the metrics JSON and the exact output schema. (3) `json.loads()` parses the response — if GPT-4o returns malformed JSON, `ValueError` is raised and the category is added to `failed_categories`. (4) `InsightStore.save()` inserts the result into `dbo.AIInsights`, storing the full structured JSON, the raw metrics used as prompt context, and a confidence score computed from data completeness.

**Q: Why temperature 0.2 for GPT-4o?**

A: Insight generation is factual analysis, not creative writing. Temperature controls sampling randomness — higher temperature produces more varied outputs, lower temperature produces more deterministic ones. At 0.2, the model consistently produces the same analytical conclusion for the same metrics, which is what you want for reproducible executive reporting. A temperature of 0 would be fully deterministic but can produce stilted prose; 0.2 allows slightly more natural language variation while maintaining factual consistency.

**Q: How did you prevent GPT-4o from hallucinating field names in the JSON output?**

A: The prompt includes the exact JSON schema with field names, type annotations, and constraints. For example: `"revenue_growth_pct": <number | null>` — GPT-4o fills in the value rather than inventing a different field name like `revenue_growth_percentage`. Without this, different calls might return `growthPct`, `revenue_growth`, or `revenueGrowthPercentage`, all of which would fail the downstream Pydantic model that expects `revenue_growth_pct`.

**Q: How is the confidence score computed?**

A: In Python, not by GPT-4o. `_compute_confidence()` checks a list of critical fields for the category — for Sales, these are `total_revenue`, `total_orders`, number of monthly trend points, number of category breakdown rows, and `revenue_growth_pct`. The confidence score is `non_null_fields / total_critical_fields`. If `total_revenue < 1000` (almost no data), the score is capped at 0.3. This approach is more reliable than asking GPT-4o to self-assess its confidence — language models are not well-calibrated for uncertainty estimation.

**Q: What happens if the insight generation call fails partway through?**

A: Each category is wrapped in a try-except. If Sales succeeds and Customers fails, Sales is saved to `dbo.AIInsights` and returned in `insight_ids`, while Customers is added to `failed_categories`. The overall status is "partial". The caller gets back all successfully generated IDs immediately — they don't need to wait for a full retry. The `force_refresh=False` default means a subsequent call for the failed category will still try (it checks `insight_exists()` per category, not overall). This partial-success pattern is better than all-or-nothing for a slow (~60s total) operation.

---

## Phase 8 — React Frontend

**Q: Why React 18 + TypeScript + Vite instead of Next.js?**

A: This is a Single Page Application behind authentication — no public-facing pages that need SEO or server-side rendering. Next.js adds complexity (server components, file-based routing, edge functions) that provides no benefit for an internal analytics tool. Vite is significantly faster than webpack for development (HMR in milliseconds vs seconds) because it uses native ES modules during development rather than bundling. TypeScript provides compile-time safety for the API response types — the Pydantic schemas in the backend map directly to TypeScript interfaces in `src/types/api.ts`, so a backend field rename causes a TypeScript error in the frontend before the app even runs.

**Q: How does the RBAC work on the frontend?**

A: `AuthContext.tsx` stores the user object (including `role`) in localStorage and provides a `hasRole(minimumRole: Role)` function. The `ROLE_LEVELS` map assigns numeric levels (`Viewer: 1, Analyst: 2, Admin: 3`). `hasRole("Analyst")` checks `ROLE_LEVELS[user.role] >= ROLE_LEVELS["Analyst"]`. `AppLayout` takes a `minRole` prop — if the current user's role doesn't meet the minimum, it renders `<Navigate to="/dashboard" />`. This is purely for UX — the actual access control lives in the backend RBAC system. The frontend RBAC just hides irrelevant navigation items and redirects unauthorised route attempts.

**Q: How does the JWT interceptor work?**

A: Axios interceptors are functions that run on every request or response before your code handles them. The request interceptor reads `insighthub_token` from localStorage and adds `Authorization: Bearer <token>` to every request header — no individual API call needs to remember to include the token. The response interceptor catches any 401 response: it clears localStorage and does a hard `window.location.href = '/login'` redirect. The hard redirect (not React Router navigate) clears all React component state, ensuring no stale data from the previous session persists.

**Q: Why use localStorage for JWT storage instead of httpOnly cookies?**

A: httpOnly cookies prevent XSS access to tokens but require same-origin requests and more complex CORS configuration (especially for a separate API on a different origin/port). localStorage is vulnerable to XSS — if an attacker injects a script, they can read the token. For this internal analytics tool the XSS risk is low (no user-generated content rendered as HTML, React escapes JSX by default). For a public-facing production app, httpOnly cookies with `SameSite=Strict` would be the correct choice.

**Q: How does the AI Insights page lazy-load detail?**

A: On mount, the page fetches `GET /api/insights` which returns a list of insight summaries — category, title, narrative, confidence score, period dates. Each `InsightCard` renders the summary immediately. When the user clicks to expand a card, the component calls `GET /api/insights/{insight_id}` for the first time and saves the result in local state. Subsequent expansions use the cached state. This lazy pattern avoids bulk-loading `StructuredJson` and `MetricsJson` (which are large NVARCHAR(MAX) columns) for cards the user never opens.

**Q: What is Recharts ComposedChart and where did you use it?**

A: `ComposedChart` renders multiple chart types (Bar, Line, Area) on the same axes and the same data set. The Support Operations page uses it to overlay the monthly ticket volume as a `Bar` and the CSAT trend as a `Line` on a dual-axis chart — left Y-axis for ticket count, right Y-axis for CSAT score (1–5 scale). A regular `LineChart` or `BarChart` can't mix chart types, so `ComposedChart` was the right component. The `YAxis yAxisId="right" orientation="right"` prop places the second scale on the right side.

---

## Phase 9 — Security & Monitoring

**Q: Walk me through how a request is secured from browser to database.**

A: Seven layers of defence: (1) TLS 1.2+ from browser to App Service — all HTTP redirected to HTTPS. (2) `TrustedHostMiddleware` rejects requests with unexpected Host headers, preventing host header injection. (3) `CORSMiddleware` with `allow_origins=[frontend_url]` — cross-origin requests from unexpected domains are rejected by the browser. (4) JWT verification — `get_current_user()` decodes and validates the HS256 signature, expiry, and token type on every request. (5) RBAC — `require_role()` checks the role claim against the endpoint's minimum role. (6) Parameterised SQL — all queries use pyodbc `?` placeholders; no user input ever reaches SQL as a string. (7) Key Vault — the JWT signing key, database credentials, and AI API keys are retrieved from Key Vault at startup via Managed Identity — never stored in App Service configuration or source code.

**Q: What is Azure Managed Identity and why is it better than storing API keys?**

A: Managed Identity is an Azure AD service principal automatically created for a resource (App Service, ADF, VM) whose credentials are managed by Azure. The application presents this identity to other Azure services without handling any credentials — Azure handles certificate rotation every ~45 days automatically. When the backend calls Key Vault to fetch secrets, it presents its Managed Identity token rather than a client secret. The token is fetched from the instance metadata service endpoint (`169.254.169.254`) inside the VM — it's never stored anywhere. Stored API keys can be leaked via source control, config dumps, or insider access to the portal; Managed Identity eliminates this attack surface entirely.

**Q: How did you handle OWASP A03 (Injection) in this project?**

A: Three defences: (1) Every SQL query uses pyodbc `?` placeholders — the query and the data are sent separately; SQL Server's ODBC driver handles parameterisation, so user input can never be interpreted as SQL syntax. (2) Query structure is hardcoded — the `granularity` parameter maps to a pre-approved dict of SQL expressions; if an attacker sends `granularity='; DROP TABLE FactSales; --`, the dict lookup returns the default `MonthYear` expression. (3) All request bodies are validated by Pydantic before any SQL runs — type coercion and length limits prevent anomalous inputs from reaching the data layer.

**Q: What custom events does Application Insights track?**

A: Four event types: `UserLogin` (username, role — fires on successful auth), `UserLoginFailed` (reason only, no username — prevents log-based enumeration), `SearchQuery` (query length, top_k, latency_ms, results_count — never the raw query text for privacy), `InsightGenerationCompleted` (triggered_by, status, generated_count, failed_categories, total_tokens). All property values are coerced to strings before dispatch. The `track_event` function is wrapped in a bare `except` — telemetry failures must never crash the application. KQL queries over these events enable brute-force detection (>10 failed logins in 5 minutes), latency SLA monitoring, and GPT-4o token cost tracking.

**Q: How does your system prevent username enumeration in the login endpoint?**

A: Two mechanisms: (1) The error response is always "Invalid username or password" — never "User not found" or "Wrong password". A distinct message for each failure lets attackers determine whether a username is valid. (2) `authenticate_user()` always calls `bcrypt.verify()` even when the user doesn't exist — it compares against a dummy hash of the same length. Without this, the response time for "user not found" would be microseconds (no bcrypt work), while "wrong password" takes ~100ms (bcrypt verification). An attacker could enumerate valid usernames by measuring response times. Always calling bcrypt.verify ensures constant ~100ms response time for both cases.

---

## Phase 10 — Infrastructure as Code & Documentation

**Q: Why Bicep instead of Terraform for Azure IaC?**

A: Bicep is the native Azure IaC language — it compiles directly to ARM JSON with no external state file. For an Azure-only project this means: (1) No state management — ARM tracks deployment state natively in Azure Resource Manager; (2) Direct Azure portal integration — deployments show in the resource group's deployment history; (3) Closer parity with new Azure features — new resource types appear in Bicep a few weeks after release vs months for the Terraform AzureRM provider. Terraform has advantages for multi-cloud or existing Terraform-heavy organisations, but for a greenfield Azure project, Bicep has less operational overhead.

**Q: Walk me through the Bicep template structure.**

A: The template declares 13 Azure resources across 6 sections: Log Analytics Workspace and Application Insights (monitoring foundation — deployed first so the connection string can be passed to App Service); Storage Account with ADLS Gen2 container (data ingestion); Azure SQL Server + Firewall + Database (data tier); Key Vault with RBAC enabled (secrets management); App Service Plan + App Service with System-Assigned Managed Identity (API tier — app settings wire the connection string, search endpoint, and OpenAI endpoint from other resource outputs); Azure AI Search (retrieval); Azure OpenAI with gpt-4o + ada-002 deployments (AI services); Azure Data Factory (orchestration); and four RBAC role assignments connecting Managed Identities to the services they need.

**Q: How are secrets handled in the Bicep parameters file?**

A: The SQL admin password is a `@secure()` parameter — Bicep never outputs it or logs it. The `parameters.json` uses a Key Vault reference via `{"reference": {"keyVault": {"id": "..."}, "secretName": "..."}}`. At deployment time, ARM fetches the secret from Key Vault and passes it directly to the template parameter without it appearing in the deployment logs or CLI output. This means even the deployment itself doesn't expose the password.

**Q: What would you change for a production deployment?**

A: Six things: (1) Enable private endpoints on SQL Server, Key Vault, and Blob Storage — remove them from the public internet. (2) Add Azure Front Door with WAF policy in front of the App Service — rate limiting, DDoS protection, geographic restrictions. (3) Switch App Service SKU to P2v3 with auto-scale rules based on CPU and request count. (4) Add Azure Redis Cache for session state and token blacklisting. (5) Enable Azure SQL Auditing to Log Analytics — full query audit trail for compliance. (6) Set up GitHub Actions CI/CD with `az deployment group create` on merge to main and `npm run build` → Azure Static Web Apps deployment for the frontend.

**Q: How would you handle zero-downtime deployment of schema changes?**

A: Use the expand-contract pattern: (1) Expand — deploy a backward-compatible schema change (add new column as nullable, add new table) before deploying new application code; both old and new app code work with the expanded schema. (2) Deploy new application code — now writing to both old and new schema. (3) Contract — once all instances are on new code, apply the breaking change (drop old column, add NOT NULL constraint). For Azure SQL, schema changes that require locks on large tables (e.g. adding a NOT NULL column to FactSales with 119K rows) should be done during a maintenance window or using `ALTER TABLE ... ADD column DEFAULT value WITH VALUES` which uses online operations in SQL Server 2012+.

---

## General / System Design

**Q: If FactSales grew to 100 million rows, what would you change?**

A: Five changes: (1) Migrate from Azure SQL (max 4TB, row-store) to Azure Synapse Analytics Dedicated SQL Pool — columnar storage and MPP architecture designed for 100B+ row workloads. (2) Replace the Python ETL with ADF pipelines + PolyBase CTAS statements for parallel bulk load. (3) Partition FactSales by `OrderDateKey` using Synapse distribution and partition strategies. (4) Move the API aggregation layer to pre-computed materialized views or Azure Analysis Services to avoid per-request full-table scans. (5) Cache KPI summary results in Azure Redis with a 15-minute TTL — the Executive Dashboard numbers don't need to be real-time.

**Q: How would you add real-time data instead of batch ETL?**

A: Replace the batch CSV pipeline with Azure Event Hubs as the ingestion layer. Each order event is published to Event Hubs. Azure Stream Analytics reads from Event Hubs and writes to two sinks: (1) Azure SQL for the transactional record; (2) Azure Data Lake Storage in Parquet format for the analytical pipeline. The API tier would query Azure SQL for near-real-time KPIs. For the executive dashboard, a 5-minute aggregate would be acceptable — full real-time updates on a dashboard are often unnecessary and add significant infrastructure complexity.

**Q: What would you monitor in production to ensure SLA?**

A: Three layers: (1) Infrastructure — App Service CPU/memory (alert if >80% for 5 minutes), SQL DTU utilisation (alert if >90%), Key Vault latency. (2) Application — request latency P95 (alert if >2s), error rate (alert if >1% in 5 minutes), failed login rate (alert if >10 in 5 minutes for brute-force detection). (3) Business metrics — insight generation success rate (alert if any category fails 3 times in a day), GPT-4o token spend (alert if daily cost exceeds budget threshold), search latency (alert if P95 >5s). All of these are queryable from Application Insights using the KQL queries defined in `docs/security/security-architecture.md`.

**Q: Describe the hardest bug you fixed in this project.**

A: The FactSales geography key mismatch. Symptom: ~30K rows had NULL GeographyKey after ETL. Diagnosis required understanding three separate layers: (1) In `loaders.py`, the old `fast_executemany` implementation padded empty strings with spaces when writing DimGeography — `StateCode=''` became `StateCode='  '`. (2) The `geo_map` builder in `transformers.py` read the StateCode value from the database without stripping, so the lookup key was `''` but the stored value was `'  '` — Python `dict` key lookup failed silently, returning `None`. (3) The `_geo_key()` helper function in `transform_fact_sales` also needed to strip whitespace from the input CSV values when building the lookup key. Fix was three `.strip()` calls in two files, plus a `--full-reload` to clean the padded dimension data. The key lesson: data quality bugs compound across pipeline stages — you need to trace data all the way from source CSV through every transformation to the final fact table row to find where the corruption enters.
