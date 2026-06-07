"""
backend/app/api/search.py

AI-powered knowledge search: natural-language question → grounded answer + source citations.

Flow:
  POST /api/search
    → embed question (Azure OpenAI text-embedding-ada-002)
    → hybrid search (BM25 + vector) with semantic re-ranking (Azure AI Search)
    → generate answer with citations (Azure OpenAI GPT-4o)
    → return SearchResponse

Requires Analyst role or above.
Index must be built first: python ai-search/run_indexer.py
"""
import logging
import time

from fastapi import APIRouter, Depends, HTTPException, status

from app.api.deps import require_role
from app.core.appinsights import track_event
from app.models.schemas import SearchRequest, SearchResponse, SearchResultSource, UserInfo
from app.services.rag_service import rag_answer

log = logging.getLogger(__name__)
router = APIRouter(prefix="/api/search", tags=["AI Search"])

_analyst = require_role("Analyst")


@router.post(
    "",
    response_model=SearchResponse,
    summary="Natural-language knowledge search (RAG)",
    description=(
        "Submit a natural-language question. The backend retrieves relevant "
        "internal documents from Azure AI Search using hybrid (keyword + vector) "
        "search with semantic re-ranking, then uses GPT-4o to generate a grounded "
        "answer with source citations. Requires the index to be built first via "
        "`python ai-search/run_indexer.py`."
    ),
)
def search(
    body: SearchRequest,
    _user: UserInfo = Depends(_analyst),
) -> SearchResponse:
    """
    RAG search endpoint.

    - 503 if Azure credentials are not configured.
    - 500 if the Azure AI Search or OpenAI service returns an unexpected error.
    - Successful response includes an answer string and a list of source documents
      with titles, excerpts, and relevance scores.
    """
    try:
        result = rag_answer(question=body.query, top_k=body.top_k)

    except RuntimeError as exc:
        # Missing credentials or RAG service initialisation failure
        log.warning("RAG service unavailable: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc

    except Exception as exc:
        log.error(
            "RAG pipeline error for query '%s': %s",
            body.query[:60], exc,
            exc_info=True,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Search service temporarily unavailable. Please try again.",
        ) from exc

    sources = [
        SearchResultSource(
            document_id=s["id"],
            title=s["title"],
            excerpt=s["excerpt"],
            score=s["score"],
            url=None,  # Source is the document title / source_file — no public URL
        )
        for s in result["sources"]
    ]

    track_event(
        "SearchQuery",
        {
            "query_length": len(body.query),
            "top_k": body.top_k,
            "latency_ms": result["latency_ms"],
            "results_count": len(sources),
        },
    )

    return SearchResponse(
        query=body.query,
        answer=result["answer"],
        sources=sources,
        latency_ms=result["latency_ms"],
    )
