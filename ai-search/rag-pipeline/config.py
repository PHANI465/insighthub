"""
ai-search/rag-pipeline/config.py

Settings for the indexer pipeline.  Reads from .env at the project root.
When run via run_indexer.py from the project root, env_file="../../.env"
resolves correctly; the tuple of fallback paths handles other CWDs.
"""
from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class RAGConfig(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=("../../.env", "../.env", ".env"),
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ── Azure AI Search ────────────────────────────────────────────────────────
    azure_search_endpoint: str = ""
    azure_search_key: str = ""
    azure_search_index: str = "insighthub-docs"

    # ── Azure OpenAI ───────────────────────────────────────────────────────────
    azure_openai_endpoint: str = ""
    azure_openai_key: str = ""
    azure_openai_deployment: str = "gpt-4o"
    azure_openai_embedding_deployment: str = "text-embedding-ada-002"
    azure_openai_api_version: str = "2024-02-01"

    # ── Azure Blob Storage (for document archival) ─────────────────────────────
    storage_account_name: str = ""
    storage_account_key: str = ""
    storage_container: str = "insighthub"
    storage_docs_prefix: str = "ai-search/documents/"

    # ── Chunking ───────────────────────────────────────────────────────────────
    chunk_size_words: int = 300       # target words per chunk (~450 tokens)
    chunk_overlap_words: int = 60     # trailing words kept in next chunk
    embedding_batch_size: int = 16    # texts per Azure OpenAI embeddings request

    # ── RAG behaviour ──────────────────────────────────────────────────────────
    rag_top_k: int = 5
    rag_answer_max_tokens: int = 800
    rag_temperature: float = 0.1


@lru_cache
def get_rag_config() -> RAGConfig:
    """Cached settings singleton."""
    return RAGConfig()
