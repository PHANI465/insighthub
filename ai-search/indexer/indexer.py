# indexer.py
# Azure AI Search indexer script for InsightHub.
# Reads documents from ai-search/documents/ (or Azure Blob), chunks them,
# generates embeddings via Azure OpenAI, and upserts them into the
# configured AI Search index. Run manually or on a schedule via ADF / cron
# whenever source documents are added or updated.
