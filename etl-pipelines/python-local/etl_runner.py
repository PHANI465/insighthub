# etl_runner.py
# Local Python alternative to ADF for running ETL steps during development.
# Reads raw CSV/JSON from a local path or Azure Blob, applies transformations
# (cleansing, normalisation, enrichment), and loads results into Azure SQL.
# Useful for rapid iteration without deploying ADF pipelines.
