# service.py
# Business logic layer between API routes and the database / Azure services.
# Contains functions for fetching metrics, triggering the insights engine,
# calling Azure AI Search, and generating Power BI embed tokens.
# Routes never touch the DB or Azure SDKs directly — they go through here.
