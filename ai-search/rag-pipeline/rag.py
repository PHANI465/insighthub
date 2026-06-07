"""
ai-search/rag-pipeline/rag.py

Retrieval-Augmented Generation (RAG) pipeline for InsightHub.

Given a natural-language question:
  1. Embed the query using Azure OpenAI.
  2. Retrieve the top-k relevant document chunks from Azure AI Search (hybrid
     keyword + vector search with semantic re-ranking).
  3. Assemble a grounded prompt from the retrieved context.
  4. Call Azure OpenAI GPT-4o to generate a cited answer.
  5. Return the answer, deduplicated source list, and latency.

This module is used for standalone indexer-side testing and as the
reference implementation.  The production backend uses
backend/app/services/rag_service.py which shares the same logic but
initialises its own Azure clients from app.core.config.
"""
import logging
import time
from typing import Any, Dict, List, Optional

from openai import AzureOpenAI

from config import get_rag_config
from searcher import HybridSearcher

log = logging.getLogger(__name__)

# ── Prompt templates ──────────────────────────────────────────────────────────

_SYSTEM_PROMPT = """\
You are an intelligent knowledge assistant for InsightHub, a business analytics platform.

Your role is to answer employee and manager questions accurately using ONLY the internal \
document excerpts provided in the context below.

Guidelines:
- Answer clearly and concisely based solely on the provided context.
- If the context does not fully address the question, say so explicitly — never invent \
information not present in the documents.
- Cite the source document title(s) you used (e.g., "According to the Annual Leave Policy…").
- Use bullet points for multi-step processes or lists.
- Keep answers under 400 words unless the question genuinely requires more detail.
"""

_CONTEXT_BLOCK = (
    "--- Document: {title} | Type: {document_type} | File: {source_file} ---\n"
    "{content}\n"
)


class RAGPipeline:
    """
    Retrieval-Augmented Generation pipeline.

    Instantiate once and call .answer() for each user question.
    Thread-safe (searcher and LLM clients are stateless after init).
    """

    def __init__(self):
        cfg = get_rag_config()
        self._searcher = HybridSearcher()
        self._llm = AzureOpenAI(
            azure_endpoint=cfg.azure_openai_endpoint,
            api_key=cfg.azure_openai_key,
            api_version=cfg.azure_openai_api_version,
        )
        self._deployment = cfg.azure_openai_deployment
        self._max_tokens = cfg.rag_answer_max_tokens
        self._temperature = cfg.rag_temperature

    def answer(
        self,
        question: str,
        top_k: int = 5,
        filter_doc_type: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Run the full RAG pipeline for a single question.

        Args:
            question: The user's natural-language question (max 500 chars, validated upstream).
            top_k: Number of document chunks to retrieve and include in context.
            filter_doc_type: Optional filter to restrict retrieval to a specific document type
                (e.g., "HR Policy", "Sales Report").

        Returns:
            {
                "answer":    str — GPT-4o's grounded answer,
                "sources":   List[dict] — deduplicated source documents,
                "latency_ms": int — total wall-clock time in milliseconds,
            }

            Each source dict:
            {
                "id": str, "title": str, "document_type": str,
                "source_file": str, "excerpt": str, "score": float
            }
        """
        t0 = time.perf_counter()

        # 1. Retrieve relevant chunks
        hits = self._searcher.search(
            question,
            top_k=top_k,
            filter_doc_type=filter_doc_type,
        )

        if not hits:
            return {
                "answer": (
                    "I could not find relevant information in the InsightHub knowledge base "
                    "for your question. Please contact the appropriate team directly for assistance."
                ),
                "sources": [],
                "latency_ms": int((time.perf_counter() - t0) * 1000),
            }

        # 2. Build context string from retrieved chunks
        context_blocks = [
            _CONTEXT_BLOCK.format(
                title=h["title"],
                document_type=h["document_type"],
                source_file=h["source_file"],
                content=h["content"],
            )
            for h in hits
        ]
        context = "\n".join(context_blocks)

        # 3. Call GPT-4o
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

        response = self._llm.chat.completions.create(
            model=self._deployment,
            messages=messages,
            temperature=self._temperature,
            max_tokens=self._max_tokens,
        )
        answer_text = response.choices[0].message.content.strip()

        # 4. Deduplicate sources by (source_file, title) — same doc may appear
        #    multiple times if multiple chunks were retrieved from it.
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
                    "document_type": h["document_type"],
                    "source_file": h["source_file"],
                    "excerpt": excerpt,
                    "score": round(h["score"], 4),
                })

        return {
            "answer": answer_text,
            "sources": sources,
            "latency_ms": int((time.perf_counter() - t0) * 1000),
        }
