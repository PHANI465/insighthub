# rag.py
# Retrieval-Augmented Generation (RAG) pipeline for InsightHub.
# Given a natural-language user query:
#   1. Embeds the query with Azure OpenAI.
#   2. Retrieves the top-k relevant document chunks from Azure AI Search.
#   3. Assembles a prompt with retrieved context and sends it to Azure OpenAI.
#   4. Returns the grounded answer with source citations.
# Called by backend/app/services/service.py for the /api/search endpoint.
