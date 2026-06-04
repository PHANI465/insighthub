// embed.js
// Power BI JavaScript SDK embedding helper for InsightHub.
// Fetches an embed token from the FastAPI backend (/api/reports/embed-token),
// then uses the powerbi-client library to render a report inside a given
// DOM container element. Handles token refresh before expiry.
