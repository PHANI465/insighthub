"""
ai-search/rag-pipeline/searcher.py

Hybrid search (BM25 keyword + cosine vector) with semantic re-ranking
over the InsightHub Azure AI Search index.

Used by:
  - rag.py (indexer-side testing / standalone use)
  - backend/app/services/rag_service.py (production, via its own Azure clients)
"""
import logging
from typing import Any, Dict, List, Optional

from azure.core.credentials import AzureKeyCredential
from azure.core.exceptions import HttpResponseError
from azure.search.documents import SearchClient
from azure.search.documents.models import VectorizedQuery

from config import get_rag_config
from embeddings import EmbeddingClient

log = logging.getLogger(__name__)

_SELECTED_FIELDS = [
    "id", "title", "content", "document_type", "source_file", "chunk_index",
]


class HybridSearcher:
    """
    Executes hybrid (BM25 + vector) search with optional semantic re-ranking.

    Semantic re-ranking requires the Azure AI Search service to be on S1 or
    higher tier.  If semantic ranking is unavailable, the searcher transparently
    falls back to standard hybrid (BM25 + vector) results.
    """

    def __init__(self):
        cfg = get_rag_config()
        self._client = SearchClient(
            endpoint=cfg.azure_search_endpoint,
            index_name=cfg.azure_search_index,
            credential=AzureKeyCredential(cfg.azure_search_key),
        )
        self._embedder = EmbeddingClient()
        self._default_top_k = cfg.rag_top_k

    def search(
        self,
        query: str,
        top_k: Optional[int] = None,
        filter_doc_type: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        Run hybrid + semantic search for a natural-language query.

        Args:
            query: The user's natural-language question.
            top_k: Number of results to return (defaults to cfg.rag_top_k).
            filter_doc_type: Optional OData filter on the document_type field,
                e.g. "HR Policy" to restrict to HR documents only.

        Returns:
            List of dicts, each containing:
              id, title, content, document_type, source_file, chunk_index, score
        """
        k = top_k or self._default_top_k
        query_vector = self._embedder.embed_single(query)

        vector_query = VectorizedQuery(
            vector=query_vector,
            k_nearest_neighbors=k,
            fields="content_vector",
        )

        odata_filter: Optional[str] = None
        if filter_doc_type:
            # Escape single quotes for OData safety
            safe = filter_doc_type.replace("'", "''")
            odata_filter = f"document_type eq '{safe}'"

        # Try semantic hybrid first; fall back to standard hybrid if unsupported
        results = self._search_semantic(query, vector_query, k, odata_filter)
        if results is None:
            log.info(
                "Semantic search unavailable (service tier); "
                "falling back to hybrid search."
            )
            results = self._search_hybrid(query, vector_query, k, odata_filter)

        return results

    def _search_semantic(
        self,
        query: str,
        vector_query: VectorizedQuery,
        top_k: int,
        odata_filter: Optional[str],
    ) -> Optional[List[Dict[str, Any]]]:
        """
        Attempt hybrid search with semantic re-ranking.
        Returns None if the service does not support semantic ranking.
        """
        try:
            raw = self._client.search(
                search_text=query,
                vector_queries=[vector_query],
                query_type="semantic",
                semantic_configuration_name="insighthub-semantic",
                query_caption="extractive",
                select=_SELECTED_FIELDS,
                filter=odata_filter,
                top=top_k,
            )
            return self._parse_results(raw)
        except HttpResponseError as exc:
            if "semantic" in str(exc).lower() or exc.status_code in (400, 422):
                return None   # Semantic not available on this tier
            raise

    def _search_hybrid(
        self,
        query: str,
        vector_query: VectorizedQuery,
        top_k: int,
        odata_filter: Optional[str],
    ) -> List[Dict[str, Any]]:
        """Standard hybrid search (BM25 + vector, no semantic re-ranking)."""
        raw = self._client.search(
            search_text=query,
            vector_queries=[vector_query],
            select=_SELECTED_FIELDS,
            filter=odata_filter,
            top=top_k,
        )
        return self._parse_results(raw)

    @staticmethod
    def _parse_results(raw) -> List[Dict[str, Any]]:
        hits: List[Dict[str, Any]] = []
        for r in raw:
            hits.append({
                "id": r["id"],
                "title": r["title"],
                "content": r["content"],
                "document_type": r.get("document_type", ""),
                "source_file": r.get("source_file", ""),
                "chunk_index": r.get("chunk_index", 0),
                "score": r.get("@search.score", 0.0),
            })
        return hits
