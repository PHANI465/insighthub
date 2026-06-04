# InsightHub API Reference

Base URL: `http://localhost:8000` (dev) / `https://api.insighthub.io` (prod)

All endpoints require a Bearer token in the `Authorization` header unless marked public.

---

## GET /api/health *(public)*
Returns service health status.

## GET /api/metrics
Returns aggregated KPI metrics for the requested time range.
Query params: `from`, `to`, `granularity` (day|week|month)

## POST /api/search
Natural-language search powered by the RAG pipeline.
Body: `{ "query": string, "top_k": number }`

## GET /api/insights
Returns AI-generated business insights and anomaly alerts.
Query params: `limit`, `category` (sales|customers|products)

## GET /api/reports/embed-token
Generates a Power BI embed token for the requested report.
Query params: `report_id`, `workspace_id`

---

*Full OpenAPI spec is auto-generated at `/docs` (Swagger UI) and `/redoc` when the backend is running.*
