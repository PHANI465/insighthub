# powerbi/reports

Stores exported Power BI report definitions (.json / template files).

Each report corresponds to a dashboard view in InsightHub:
- `sales_overview` — revenue KPIs, trends, and regional breakdown
- `customer_analytics` — cohort analysis, churn signals, LTV
- `product_performance` — top/bottom performers, inventory turns
- `ai_insights_board` — AI-generated anomaly and opportunity summaries

`.pbix` files are excluded from git (see `.gitignore`). Only the JSON
metadata / template representations are tracked here.
