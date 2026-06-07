"""
ai-search/rag-pipeline/embeddings.py

Azure OpenAI embedding client with batching and exponential-backoff retry.
Produces 1536-dimensional vectors using text-embedding-ada-002 (default) or
any other deployed embedding model.
"""
import logging
import time
from typing import List

from openai import AzureOpenAI, APIError, RateLimitError

from config import get_rag_config

log = logging.getLogger(__name__)

EMBEDDING_DIMENSIONS = 1536  # text-embedding-ada-002 output size


class EmbeddingClient:
    """
    Thin wrapper around Azure OpenAI embeddings.

    Handles:
    - Batching (configurable batch size to stay within API limits)
    - Exponential-backoff retry on rate-limit errors
    - Ordering guarantee (sorts by index before returning)
    """

    def __init__(self):
        cfg = get_rag_config()
        self._client = AzureOpenAI(
            azure_endpoint=cfg.azure_openai_endpoint,
            api_key=cfg.azure_openai_key,
            api_version=cfg.azure_openai_api_version,
        )
        self._model = cfg.azure_openai_embedding_deployment
        self._batch_size = cfg.embedding_batch_size

    def embed_single(self, text: str) -> List[float]:
        """Embed a single text string. Returns a list of floats."""
        return self._embed_with_retry([text])[0]

    def embed_batch(self, texts: List[str]) -> List[List[float]]:
        """
        Embed a list of texts, processing in batches of self._batch_size.
        Returns embeddings in the same order as the input list.
        """
        if not texts:
            return []

        all_embeddings: List[List[float]] = []
        for i in range(0, len(texts), self._batch_size):
            batch = texts[i: i + self._batch_size]
            all_embeddings.extend(self._embed_with_retry(batch))
            # Brief pause between batches to stay under TPM limits
            if i + self._batch_size < len(texts):
                time.sleep(0.1)

        return all_embeddings

    def _embed_with_retry(
        self,
        texts: List[str],
        max_attempts: int = 4,
    ) -> List[List[float]]:
        """
        Call the embeddings API with exponential-backoff retry.
        Raises RuntimeError if all attempts fail.
        """
        for attempt in range(1, max_attempts + 1):
            try:
                response = self._client.embeddings.create(
                    input=texts,
                    model=self._model,
                )
                # Sort by index to guarantee ordering (API does not guarantee order)
                sorted_data = sorted(response.data, key=lambda item: item.index)
                return [item.embedding for item in sorted_data]

            except RateLimitError:
                wait_secs = 2 ** attempt  # 2, 4, 8, 16 seconds
                log.warning(
                    "Rate-limited by Azure OpenAI embeddings (attempt %d/%d); "
                    "waiting %ds before retry.",
                    attempt, max_attempts, wait_secs,
                )
                time.sleep(wait_secs)

            except APIError as exc:
                log.error(
                    "Azure OpenAI API error on attempt %d/%d: %s",
                    attempt, max_attempts, exc,
                )
                if attempt == max_attempts:
                    raise

        raise RuntimeError(
            f"Embedding failed after {max_attempts} attempts. "
            "Check AZURE_OPENAI_ENDPOINT, AZURE_OPENAI_KEY, and the "
            "embedding deployment name in your .env file."
        )
