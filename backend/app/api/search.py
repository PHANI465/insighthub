"""
backend/app/api/search.py

AI-powered search routes using Azure AI Search + GPT-4o RAG pipeline.

  POST /api/search   → natural-language query → grounded answer with sources

The full RAG pipeline is implemented in Phase 6 (ai-search/).
This module implements the API surface and calls the pipeline.
"""

import logging
import time
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status

from app.api.deps import get_current_user, require_role
from app.core.appinsights import track_event
from app.core.config import get_settings
from app.models.schemas import SearchRequest, SearchResponse, SearchResultSource, UserInfo

log = logging.getLogger(__name__)
router = APIRouter(prefix="/api/search", tags=["AI Search"])
settings = get_settings()

_analyst = require_role("Analyst")


@router.post(
    "",
    response_model=SearchResponse,
    summary="Natural-language knowledge search (RAG)",
    description=(
        "Submit a natural-language question. The backend retrieves relevant "
        "internal documents from Azure AI Search and uses GPT-4o to generate "
        "a grounded answer with source citations."
    ),
)
def search(
    body: SearchRequest,
    _user: UserInfo = Depends(_analyst),
) -> SearchResponse:
    """
    RAG search endpoint.

    Phase 6 will wire this to the full ai-search/rag-pipeline/rag.py.
    Until then, returns a structured placeholder that matches the final
    response schema so the frontend can be built against it immediately.
    """
    start = time.perf_counter()

    # Validate Azure AI Search is configured
    if not settings.azure_search_endpoint or not settings.azure_search_key:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Azure AI Search is not configured. Set AZURE_SEARCH_ENDPOINT and AZURE_SEARCH_KEY.",
        )

    try:
        # Phase 6 will replace this block with the real RAG pipeline call:
        # from ai_search.rag_pipeline.rag import run_rag
        # result = run_rag(query=body.query, top_k=body.top_k)

        # Placeholder response until Phase 6 is complete
        answer = (
            f"[AI Search configured — full RAG pipeline wired in Phase 6] "
            f"Your query '{body.query}' will be answered using hybrid search "
            f"over internal InsightHub documents via Azure AI Search + GPT-4o."
        )
        sources = [
            SearchResultSource(
                document_id="placeholder-001",
                title="Azure AI Search RAG Integration",
                excerpt="Full RAG pipeline will be connected in Phase 6.",
                score=0.95,
            )
        ]

        latency_ms = int((time.perf_counter() - start) * 1000)
        track_event(
            "SearchQuery",
            {
                "query_length": len(body.query),
                "top_k": body.top_k,
                "latency_ms": latency_ms,
                "results_count": len(sources),
            },
        )

        return SearchResponse(
            query=body.query,
            answer=answer,
            sources=sources,
            latency_ms=latency_ms,
        )

    except Exception as exc:
        log.error("Search failed for query '%s': %s", body.query[:50], exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Search service temporarily unavailable. Please try again.",
        ) from exc
