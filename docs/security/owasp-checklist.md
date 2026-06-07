# InsightHub — OWASP Top 10 (2021) Security Checklist

Every backend endpoint audited against the OWASP Top 10. Status: ✅ Protected | ⚠️ Partial | ❌ Gap.

---

## Endpoints Reference

| Method | Path                              | Min Role | Handler              |
|--------|-----------------------------------|----------|----------------------|
| POST   | `/api/auth/token`                 | Public   | auth.login           |
| POST   | `/api/auth/refresh`               | Public   | auth.refresh_token   |
| GET    | `/api/auth/me`                    | Any JWT  | auth.get_me          |
| GET    | `/api/metrics/dashboard`          | Viewer   | metrics.get_dashboard |
| GET    | `/api/metrics/revenue`            | Viewer   | metrics.get_revenue_trend |
| GET    | `/api/metrics/campaigns`          | Viewer   | metrics.get_campaign_roi |
| GET    | `/api/metrics/customers`          | Analyst  | metrics.get_customer_segments |
| GET    | `/api/metrics/products`           | Analyst  | metrics.get_product_performance |
| GET    | `/api/metrics/support`            | Analyst  | metrics.get_support_metrics |
| POST   | `/api/search`                     | Analyst  | search.search        |
| GET    | `/api/insights`                   | Viewer   | insights.get_insights |
| GET    | `/api/insights/{insight_id}`      | Viewer   | insights.get_insight_detail |
| POST   | `/api/insights/generate`          | Admin    | insights.generate_insights |
| GET    | `/api/health`                     | Public   | main.health_check    |

---

## A01 — Broken Access Control

**Risk**: Users access data or actions beyond their authorisation.

### What Is Protected

| Control | Implementation | Endpoints |
|---------|---------------|-----------|
| JWT required on all protected routes | `get_current_user` FastAPI dependency; returns 401 if token missing or invalid | All except `/api/auth/token`, `/api/auth/refresh`, `/api/health` |
| Role hierarchy enforcement | `require_role(min_role)` checks `ROLE_LEVELS[user.role] >= ROLE_LEVELS[min_role]` | All protected routes |
| Object-level authorisation | Insights are public within the authorised role; no per-user row filtering needed (system data, not personal) | `/api/insights/{insight_id}` |
| Admin-only generation | `POST /api/insights/generate` requires Admin; returns 403 for Viewer/Analyst | Insight generation |
| CORS origin restriction | `CORSMiddleware` accepts requests only from `ALLOWED_ORIGINS` | All endpoints |
| Trusted host enforcement | `TrustedHostMiddleware` rejects unexpected `Host` headers | All endpoints |

### Remaining Gaps

| Gap | Risk | Status |
|-----|------|--------|
| No per-tenant isolation (single-tenant app) | N/A for single-org tool | Acceptable |
| No IP allowlisting on `/api/auth/token` | Brute-force possible from any IP | ⚠️ Add rate limiting (Azure API Management or SlowAPI) |

---

## A02 — Cryptographic Failures

**Risk**: Sensitive data exposed due to weak or absent encryption.

### What Is Protected

| Control | Implementation | Location |
|---------|---------------|----------|
| Passwords stored as bcrypt hashes | `passlib[bcrypt]` with default work factor 12 | `auth_service.py` `get_password_hash()` |
| JWT signed with HS256 | `python-jose` with 256-bit secret key from Key Vault | `security.py` `create_access_token()` |
| TLS 1.2+ enforced in transit | App Service `minTlsVersion: 1.2` + `httpsOnly: true`; SQL `Encrypt=yes` | Bicep + `config.py` |
| No secrets in source code | All secrets via `.env` (dev) or Key Vault (prod) | `config.py`, `keyvault.py` |
| Azure-managed encryption at rest | Azure SQL TDE enabled by default; Blob Storage SSE with Microsoft-managed keys | Azure platform default |
| Refresh tokens are separate JWT | Different expiry (7 days), `type: refresh` claim prevents use as access token | `security.py` |

### Remaining Gaps

| Gap | Risk | Status |
|-----|------|--------|
| JWT secret in `.env` for local dev | Low — dev environment only | ⚠️ Use Key Vault for staging/prod |
| No token blacklist / revocation | Stolen token valid until expiry (60 min) | ⚠️ Acceptable for MVP; add Redis token store for production |
| Embedding API key in `.env` | Medium — exposes OpenAI billing | ⚠️ Switch to Managed Identity for production |

---

## A03 — Injection

**Risk**: Untrusted data sent to a SQL interpreter or OS command.

### What Is Protected

| Control | Implementation | Location |
|---------|---------------|----------|
| All SQL uses parameterised `?` placeholders | pyodbc never receives user-controlled strings interpolated into SQL | All `execute_query()` calls in `metrics_service.py`, `insights_service.py`, `auth_service.py` |
| Column names are hardcoded constants | `granularity` query param maps to a pre-approved dict of SQL expressions; no user string ever reaches SQL structure | `metrics_service.py` `get_revenue_trend()` |
| No OS command execution | Backend has no `subprocess`, `os.system`, or `eval` calls | Entire codebase |
| Pydantic validates all request bodies | `LoginRequest`, `SearchRequest`, `GenerateInsightRequest` enforce types and length limits before any SQL is run | `schemas.py` |
| Path parameter UUID validation | `/api/insights/{insight_id}` enforces `min_length=36, max_length=36` on the path parameter | `insights.py` Path() |
| No raw string interpolation for user queries | RAG search sends `body.query` to the AI Search SDK's `search_text` field, never into SQL | `rag_service.py` |

### Test Evidence

```python
# This cannot inject SQL — pyodbc sends username as a parameter, not in the query string
cur.execute(
    "SELECT ... FROM dbo.AppUsers WHERE Username = ? AND IsActive = 1",
    (body.username,)   # ← always a parameter
)
```

The granularity whitelist:
```python
period_expr = {
    "day": "CONVERT(VARCHAR(10), OrderDate, 120)",
    "week": "...",
    "month": "MonthYear",
    "quarter": "...",
    "year": "CAST(CalendarYear AS VARCHAR)",
}.get(granularity, "MonthYear")   # unknown → safe default
```

### Remaining Gaps

None material for the current threat model.

---

## A04 — Insecure Design

**Risk**: Design flaws that cannot be fixed by correct implementation.

### What Is Protected

| Design Decision | Rationale |
|----------------|-----------|
| Viewer role can only read aggregated metrics, never raw customer PII | Data minimisation — frontend never receives individual customer records |
| AI Insights generated only on Admin trigger, not automatically | Prevents uncontrolled GPT-4o token spend; Admin oversight on AI output |
| JWT tokens are short-lived (60 min access, 7 day refresh) | Limits blast radius of token theft |
| Bcrypt always runs even if user not found (timing-safe auth) | Prevents username enumeration via response time differences |
| `track_failed_login()` omits username from App Insights | Prevents log aggregation services from revealing valid usernames |
| Search queries sent to Azure AI Search, not to SQL | Prevents query injection into the reporting database |
| RAG pipeline uses fixed Azure endpoints from config, not user-supplied URLs | Prevents SSRF via user-controlled endpoint |

### Remaining Gaps

| Gap | Risk |
|-----|------|
| Synchronous insight generation can time out long-running admin requests | ⚠️ Move to background task queue (Azure Service Bus + Worker) for production |

---

## A05 — Security Misconfiguration

**Risk**: Default settings, unnecessary features, or verbose error messages expose the system.

### What Is Protected

| Control | Implementation | Status |
|---------|---------------|--------|
| `/docs` and `/redoc` only in dev | FastAPI `docs_url="/docs"` — acceptable for internal tool; disable in production by setting `docs_url=None` | ⚠️ Disable in prod |
| Generic error messages on 500s | Global exception handler returns `{"detail": "An internal server error occurred"}` — no stack traces to clients | ✅ |
| Debug mode off by default | `Settings.debug = False` in `config.py`; only `True` if `.env` explicitly sets `DEBUG=true` | ✅ |
| CORS restricted | `ALLOWED_ORIGINS=http://localhost:3000` — must be changed to production URL before deployment | ⚠️ Update for prod |
| SQL account has minimal permissions | App login should have `db_datareader` + specific stored proc permissions; no DDL rights | ⚠️ Grant explicit minimal SQL RBAC |
| Azure Blob container is private | Container `publicAccess: 'None'` in Bicep | ✅ |
| Storage account rejects public access | `allowBlobPublicAccess: false` in Bicep | ✅ |
| TrustedHostMiddleware | Rejects requests with invalid `Host` headers | ✅ |
| GZipMiddleware | Compresses responses ≥ 1 KB — reduces bandwidth but no security impact | N/A |
| FTPS disabled on App Service | `ftpsState: 'Disabled'` in Bicep | ✅ |
| Minimum TLS 1.2 on SQL Server | `minimalTlsVersion: '1.2'` in Bicep | ✅ |

---

## A06 — Vulnerable and Outdated Components

**Risk**: Known CVEs in dependencies are exploitable.

### What Is Protected

| Control | Implementation |
|---------|---------------|
| All dependencies pinned with exact versions | `backend/requirements.txt` uses `==` not `>=` for every package |
| No known CVEs at time of deployment | Versions chosen (FastAPI 0.111, python-jose 3.3.0, passlib 1.7.4) are current stable |
| OS packages managed by Azure App Service | Platform patches applied by Azure — no manual OS maintenance |

### Version Audit (June 2025)

| Package | Version | Notes |
|---------|---------|-------|
| fastapi | 0.111.0 | Current stable |
| uvicorn | 0.29.0 | Current stable |
| python-jose | 3.3.0 | Use `cryptography` extra for modern backends |
| passlib | 1.7.4 | bcrypt 4.0.1 in Anaconda env — compatible |
| pyodbc | 5.1.0 | Current stable with ODBC Driver 18 |
| openai | 1.35.0 | Current stable |
| azure-search-documents | 11.6.0 | Current stable |

### Remaining Gaps

| Gap | Action |
|-----|--------|
| No automated dependency scanning | ⚠️ Add `pip-audit` to CI pipeline or enable GitHub Dependabot |
| `python-jose` has known limitations with some JWT algorithms | Use `cryptography` extra (already included via `python-jose[cryptography]`) |

---

## A07 — Identification and Authentication Failures

**Risk**: Weak authentication allows account takeover.

### What Is Protected

| Control | Implementation | Code Location |
|---------|---------------|---------------|
| Bcrypt password hashing | `passlib.hash.bcrypt.verify()` — constant-time comparison | `auth_service.py` `verify_password()` |
| Timing-safe authentication | `authenticate_user()` always calls `bcrypt.verify()` even if user not found (dummy hash comparison) | `auth_service.py` |
| Generic error message | Returns "Invalid username or password" for both wrong user and wrong password | `auth.py` login |
| Short-lived access tokens | 60-minute expiry; `exp` claim validated on every request | `security.py` |
| Refresh token type check | Refresh tokens have `type: refresh` claim; access endpoints reject refresh tokens | `security.py` `decode_refresh_token()` |
| Login events tracked | Successful logins tracked with username + role; failures tracked without username | `auth.py`, `appinsights.py` |
| Last login timestamp recorded | `record_login()` updates `LastLogin` in `dbo.AppUsers` | `auth_service.py` |
| Password complexity enforced | Demo passwords use uppercase + lowercase + digit + special character | Seeded in `database/seed_users.py` |

### Remaining Gaps

| Gap | Risk | Action |
|-----|------|--------|
| No rate limiting on `/api/auth/token` | Brute force possible | ⚠️ Add SlowAPI or Azure APIM policy |
| No MFA | Medium for production use | ⚠️ Add Azure AD B2C or TOTP for production |
| Refresh token not single-use | Compromised refresh token can be used until expiry | ⚠️ Add token family tracking in Redis |

---

## A08 — Software and Data Integrity Failures

**Risk**: Code/data can be modified without detection; insecure deserialisation.

### What Is Protected

| Control | Implementation |
|---------|---------------|
| No `pickle`, `yaml.load()`, or other unsafe deserialisation | Only `json.loads()` used; applied to App Insights JSON responses and AI insight JSON output | 
| AI output validated before storage | GPT-4o responses parsed with `json.loads()` — raises `ValueError` if malformed; never executed | `insights_service.py` `_call()` |
| Pydantic models for all request/response types | `LoginRequest`, `SearchRequest`, etc. enforce schema before any processing | `schemas.py` |
| Input length limits | `SearchRequest.query` has `max_length` enforced by Pydantic; insight_id path param is UUID length | `schemas.py` |
| No `eval()` or dynamic code execution | Grep-verified — none present in backend codebase | |

---

## A09 — Security Logging and Monitoring Failures

**Risk**: Breaches go undetected; insufficient audit trail for incident response.

### What Is Protected

| Control | Implementation | App Insights Location |
|---------|---------------|----------------------|
| All login attempts logged | Success: `track_event("UserLogin", ...)` + `log.info`; Failure: `track_failed_login()` + `log.warning` | `traces` table |
| All searches tracked | `track_event("SearchQuery", ...)` with latency and result count | `traces` table |
| All insight generation tracked | `track_event("InsightGenerationCompleted", ...)` with token usage | `traces` table |
| All 500 errors captured | Global exception handler calls `track_exception()` | `exceptions` table |
| Unhandled exceptions routed to App Insights | Root logger has `AzureLogHandler` at WARNING+ | `exceptions` table |
| Last login timestamp recorded in SQL | `dbo.AppUsers.LastLogin` updated on each successful auth | Azure SQL |

### KQL Alerts to Configure

```kusto
-- Alert: >10 failed logins in 5 minutes (brute force)
traces
| where customDimensions.event_name == "UserLoginFailed"
| summarize count() by bin(timestamp, 5m)
| where count_ > 10

-- Alert: any 500 error on auth endpoint
exceptions
| where operation_Name contains "auth"

-- Alert: search latency > 10 seconds
traces
| where customDimensions.event_name == "SearchQuery"
| where toint(customDimensions.latency_ms) > 10000
```

### Remaining Gaps

| Gap | Action |
|-----|--------|
| No Azure Monitor alerts configured | ⚠️ Create alert rules from KQL queries above |
| Logs not exported to SIEM | ⚠️ Add Log Analytics → Microsoft Sentinel export for production |
| Database audit log not enabled | ⚠️ Enable Azure SQL Auditing to Log Analytics |

---

## A10 — Server-Side Request Forgery (SSRF)

**Risk**: Backend makes HTTP requests to attacker-controlled URLs.

### What Is Protected

| Control | Implementation |
|---------|---------------|
| Azure AI Search endpoint is from config, not user input | `settings.azure_search_endpoint` set in `.env` / Key Vault; user query goes to `search_text`, not the endpoint | `rag_service.py` |
| Azure OpenAI endpoint is from config, not user input | `settings.azure_openai_endpoint` from config; user query is a string parameter to the API, not a URL | `rag_service.py`, `insights_service.py` |
| No user-supplied URLs in any backend call | No endpoint accepts a URL that the backend then fetches | Entire codebase |
| No internal metadata service access | App Service blocks IMDS access from app code by default | Azure platform |

### Remaining Gaps

None material. The application makes outbound calls only to Azure's own service endpoints (ai.azure.com, openai.azure.com, database.windows.net) which are validated configuration, not user input.

---

## Summary Scorecard

| OWASP Category                        | Status | Critical Gaps |
|---------------------------------------|--------|---------------|
| A01 Broken Access Control             | ✅     | Add rate limiting on auth |
| A02 Cryptographic Failures            | ✅     | Use Key Vault in prod (supported, not yet deployed) |
| A03 Injection                         | ✅     | None |
| A04 Insecure Design                   | ✅     | Move insight generation to async queue in prod |
| A05 Security Misconfiguration         | ⚠️     | Disable /docs in prod, restrict CORS to prod URL |
| A06 Vulnerable and Outdated Components| ✅     | Add pip-audit to CI |
| A07 ID and Authentication Failures    | ⚠️     | Add rate limiting, consider MFA for prod |
| A08 Software and Data Integrity       | ✅     | None |
| A09 Security Logging and Monitoring   | ✅     | Configure Azure Monitor alerts |
| A10 SSRF                              | ✅     | None |

**Overall posture**: Strong for an internal analytics tool. Priority actions before public-facing deployment: rate limiting on auth, Key Vault for all secrets, disable Swagger UI, enable Azure Monitor alerts.
