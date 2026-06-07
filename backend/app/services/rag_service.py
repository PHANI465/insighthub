"""
backend/app/services/rag_service.py

Production RAG service for the /api/search endpoint.

Implements the same Retrieve → Augment → Generate flow as the standalone
ai-search/rag-pipeline/rag.py, but initialised from app.core.config so it
integrates cleanly with the FastAPI dependency-injection system.

Thread safety:
  _RAGService is stateless after __init__ (Azure clients are thread-safe).
  The singleton is lazily constructed on the first call to rag_answer().
"""
import logging
import time
from typing import Any, Dict, List, Optional

from azure.core.credentials import AzureKeyCredential
from azure.core.exceptions import HttpResponseError
from azure.search.documents import SearchClient
from azure.search.documents.models import VectorizedQuery
from openai import AzureOpenAI, APIError, RateLimitError

from app.core.config import get_settings

log = logging.getLogger(__name__)

# ── Prompt ────────────────────────────────────────────────────────────────────

_SYSTEM_PROMPT = """\
You are an intelligent knowledge assistant for InsightHub, a business analytics platform.

Answer employee and manager questions accurately using ONLY the internal document excerpts \
provided in the context below.

Guidelines:
- Answer clearly and concisely based solely on the provided context.
- If the context does not fully address the question, say so explicitly — never invent \
information not present in the documents.
- Cite the source document title(s) you used (e.g., "According to the Annual Leave Policy…").
- Use bullet points for multi-step processes or lists.
- Keep answers under 400 words unless the question genuinely requires more detail.
"""

_CONTEXT_BLOCK = (
    "--- Document: {title} | Type: {document_type} ---\n"
    "{content}\n"
)

_AZURE_AI_SEARCH_API_VERSION = "2024-02-01"  # noqa — used by the service, not config
_OPENAI_API_VERSION = "2024-02-01"

_SELECTED_FIELDS = [
    "id", "title", "content", "document_type", "source_file", "chunk_index",
]


# ── Internal singleton ────────────────────────────────────────────────────────

class _RAGService:
    """
    Holds Azure Search + OpenAI clients and executes the RAG pipeline.
    Constructed once on first use via get_rag().
    """

    def __init__(self) -> None:
        cfg = get_settings()
        credential = AzureKeyCredential(cfg.azure_search_key)

        self._search_client = SearchClient(
            endpoint=cfg.azure_search_endpoint,
            index_name=cfg.azure_search_index,
            credential=credential,
        )
        self._openai = AzureOpenAI(
            azure_endpoint=cfg.azure_openai_endpoint,
            api_key=cfg.azure_openai_key,
            api_version=_OPENAI_API_VERSION,
        )
        self._embedding_model = cfg.azure_openai_embedding_deployment
        self._chat_model = cfg.azure_openai_deployment

    # ── Embedding ─────────────────────────────────────────────────────────────

    def _embed(self, text: str) -> List[float]:
        """Embed a single string; raises APIError on failure."""
        response = self._openai.embeddings.create(
            input=text,
            model=self._embedding_model,
        )
        return response.data[0].embedding

    # ── Search ────────────────────────────────────────────────────────────────

    def _hybrid_search(
        self,
        query: str,
        query_vector: List[float],
        top_k: int,
    ) -> List[Dict[str, Any]]:
        """
        Hybrid (BM25 + vector) search with semantic re-ranking.
        Falls back to standard hybrid if semantic is unavailable.
        """
        vector_query = VectorizedQuery(
            vector=query_vector,
            k_nearest_neighbors=top_k,
            fields="content_vector",
        )

        # Attempt semantic hybrid
        try:
            raw = self._search_client.search(
                search_text=query,
                vector_queries=[vector_query],
                query_type="semantic",
                semantic_configuration_name="insighthub-semantic",
                query_caption="extractive",
                select=_SELECTED_FIELDS,
                top=top_k,
            )
            return self._parse_hits(raw)
        except HttpResponseError as exc:
            if exc.status_code in (400, 422) or "semantic" in str(exc).lower():
                # Service tier does not support semantic ranking — fall back
                log.debug("Semantic ranking unavailable; using standard hybrid.")
            else:
                raise

        # Standard hybrid fallback
        raw = self._search_client.search(
            search_text=query,
            vector_queries=[vector_query],
            select=_SELECTED_FIELDS,
            top=top_k,
        )
        return self._parse_hits(raw)

    @staticmethod
    def _parse_hits(raw) -> List[Dict[str, Any]]:
        return [
            {
                "id": r["id"],
                "title": r["title"],
                "content": r["content"],
                "document_type": r.get("document_type", ""),
                "source_file": r.get("source_file", ""),
                "score": r.get("@search.score", 0.0),
            }
            for r in raw
        ]

    # ── RAG pipeline ──────────────────────────────────────────────────────────

    def answer(self, question: str, top_k: int = 5) -> Dict[str, Any]:
        """
        Full RAG pipeline: embed → retrieve → generate → return.

        Returns:
            {
                "answer":     str,
                "sources":    List[dict],
                "latency_ms": int,
            }
        """
        t0 = time.perf_counter()

        # 1. Embed the question
        query_vector = self._embed(question)

        # 2. Retrieve relevant chunks
        hits = self._hybrid_search(question, query_vector, top_k)

        if not hits:
            return {
                "answer": (
                    "No relevant information was found in the InsightHub knowledge base "
                    "for your question. Please contact the appropriate team directly."
                ),
                "sources": [],
                "latency_ms": int((time.perf_counter() - t0) * 1000),
            }

        # 3. Build grounded context
        context = "\n".join(
            _CONTEXT_BLOCK.format(
                title=h["title"],
                document_type=h["document_type"],
                content=h["content"],
            )
            for h in hits
        )

        # 4. Generate answer with GPT-4o
        messages = [
            {"role": "system", "content": _SYSTEM_PROMPT},
            {
                "role": "user",
                "content": (
                    f"Context from internal InsightHub documents:\n\n"
                    f"{context}\n\n"
                    f"Question: {question}"
                ),
            },
        ]

        completion = self._openai.chat.completions.create(
            model=self._chat_model,
            messages=messages,
            temperature=0.1,
            max_tokens=800,
        )
        answer_text = completion.choices[0].message.content.strip()

        # 5. Build deduplicated source list (same document can match multiple chunks)
        seen: set = set()
        sources: List[Dict[str, Any]] = []
        for h in hits:
            key = (h["source_file"], h["title"])
            if key not in seen:
                seen.add(key)
                excerpt = h["content"][:300]
                if len(h["content"]) > 300:
                    excerpt += "…"
                sources.append({
                    "id": h["id"],
                    "title": h["title"],
                    "document_type": h.get("document_type", ""),
                    "source_file": h.get("source_file", ""),
                    "excerpt": excerpt,
                    "score": round(h["score"], 4),
                })

        return {
            "answer": answer_text,
            "sources": sources,
            "latency_ms": int((time.perf_counter() - t0) * 1000),
        }


# ── Public interface ──────────────────────────────────────────────────────────

_rag_instance: Optional[_RAGService] = None
_rag_init_error: Optional[str] = None


def get_rag() -> Optional[_RAGService]:
    """
    Return the singleton _RAGService, initialising it on first call.
    Returns None if required credentials are missing or initialisation failed.
    """
    global _rag_instance, _rag_init_error

    if _rag_instance is not None:
        return _rag_instance
    if _rag_init_error is not None:
        return None

    cfg = get_settings()
    required = {
        "AZURE_SEARCH_ENDPOINT": cfg.azure_search_endpoint,
        "AZURE_SEARCH_KEY": cfg.azure_search_key,
        "AZURE_OPENAI_ENDPOINT": cfg.azure_openai_endpoint,
        "AZURE_OPENAI_KEY": cfg.azure_openai_key,
    }
    missing = [k for k, v in required.items() if not v]
    if missing:
        _rag_init_error = f"Missing configuration: {', '.join(missing)}"
        log.warning("RAG service disabled — %s", _rag_init_error)
        return None

    try:
        _rag_instance = _RAGService()
        log.info("RAG service initialised (index: %s)", cfg.azure_search_index)
    except Exception as exc:
        _rag_init_error = str(exc)
        log.error("RAG service init failed: %s", exc)

    return _rag_instance


def rag_answer(question: str, top_k: int = 5) -> Dict[str, Any]:
    """
    Public entry point called by the /api/search route.

    Raises:
        RuntimeError: If the RAG service is not configured or failed to initialise.
        APIError: If Azure OpenAI returns an error.
        HttpResponseError: If Azure AI Search returns an error.
    """
    svc = get_rag()
    if svc is None:
        raise RuntimeError(
            _rag_init_error
            or "RAG service is not available. Check Azure credentials in .env."
        )
    return svc.answer(question, top_k=top_k)
