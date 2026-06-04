# InsightHub

> End-to-end data analytics and AI-powered insights platform built on Azure.

## Overview

InsightHub ingests raw business data, transforms it through ETL pipelines, stores it in Azure SQL,
surfaces interactive Power BI dashboards, and exposes an AI-powered search and natural-language
insights engine through a FastAPI backend and React frontend.

## Repository Structure

```
insighthub/
├── data-generation/      Synthetic data generators for dev/testing
├── etl-pipelines/        ADF templates and local Python ETL scripts
├── database/             SQL schema definitions and migration files
├── backend/              FastAPI REST API (Python)
├── frontend/             React dashboard application
├── powerbi/              Power BI datasets, reports, and embedding helpers
├── ai-search/            Azure AI Search indexer and RAG pipeline
├── insights-engine/      AI-driven insights and anomaly detection logic
├── infrastructure/       Bicep / ARM templates for Azure provisioning
└── docs/                 Architecture diagrams and API reference
```

## Quick Start

1. Copy `.env.example` → `.env` and fill in your Azure credentials.
2. Run `docker-compose up` to start backend, frontend, and database locally.
3. See `docs/architecture/` for the full system design.

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Cloud | Azure (SQL, ADLS, ADF, AI Search, OpenAI) |
| ETL | Azure Data Factory + Python |
| Backend | FastAPI, SQLAlchemy, Pydantic |
| Frontend | React, Recharts, Power BI Embedded |
| AI | Azure OpenAI, Azure AI Search (RAG) |
| IaC | Bicep / ARM |
