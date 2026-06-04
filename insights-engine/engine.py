# engine.py
# InsightHub AI Insights Engine.
# Periodically queries the Azure SQL database for recent metrics, detects
# anomalies (statistical thresholds + ML models), and generates plain-English
# insight summaries using Azure OpenAI (GPT-4o).
# Results are written back to the `insights` table and surfaced via
# the /api/insights endpoint in the FastAPI backend.
