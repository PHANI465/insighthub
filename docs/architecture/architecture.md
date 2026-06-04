# InsightHub — Architecture Overview

This document describes the end-to-end system design for InsightHub.

## High-Level Architecture

```
Raw Data Sources
      │
      ▼
Azure Data Lake Storage Gen2   ◄── data-generation/ (dev seeds)
      │
      ▼
Azure Data Factory (ETL)       ◄── etl-pipelines/adf-templates/
      │
      ▼
Azure SQL Database             ◄── database/schema/ + migrations/
      │
      ├──► FastAPI Backend     ◄── backend/
      │         │
      │         ├──► Azure AI Search (RAG)   ◄── ai-search/
      │         ├──► Azure OpenAI (GPT-4o)   ◄── insights-engine/
      │         └──► Power BI REST API       ◄── powerbi/embedding/
      │
      └──► Power BI Service    ◄── powerbi/datasets/ + reports/
                │
                ▼
          React Frontend       ◄── frontend/
```

## Component Descriptions

| Component | Purpose |
|-----------|---------|
| ADLS Gen2 | Raw data landing zone |
| ADF | Orchestrates ELT from ADLS → SQL |
| Azure SQL | Operational data store + aggregation layer |
| FastAPI | REST API; business logic and service orchestration |
| Azure AI Search | Vector + keyword search over business documents |
| Azure OpenAI | Embedding generation and insight summarisation |
| Power BI | Interactive dashboards embedded in the React frontend |
| React | SPA dashboard consumed by business users |
| Bicep | Infrastructure-as-Code for all Azure resources |
