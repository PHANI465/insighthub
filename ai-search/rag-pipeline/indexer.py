"""
ai-search/rag-pipeline/indexer.py

Creates (or recreates) the Azure AI Search index and uploads all document chunks
with their embedding vectors.  Called by ai-search/run_indexer.py.

Index schema:
  - Full-text searchable: title, content
  - Filterable: document_type, source_file
  - Vector (1536-dim HNSW cosine): content_vector
  - Semantic configuration: insighthub-semantic
"""
import hashlib
import logging
from pathlib import Path
from typing import List

from azure.core.credentials import AzureKeyCredential
from azure.core.exceptions import HttpResponseError, ResourceNotFoundError
from azure.search.documents import SearchClient
from azure.search.documents.indexes import SearchIndexClient
from azure.search.documents.indexes.models import (
    HnswAlgorithmConfiguration,
    SearchField,
    SearchFieldDataType,
    SearchIndex,
    SemanticConfiguration,
    SemanticField,
    SemanticPrioritizedFields,
    SemanticSearch,
    VectorSearch,
    VectorSearchProfile,
)

from chunker import load_all_documents
from config import get_rag_config
from embeddings import EmbeddingClient

log = logging.getLogger(__name__)

_VECTOR_DIMS = 1536   # text-embedding-ada-002 output dimensions
_INDEX_NAME_DEFAULT = "insighthub-docs"


# ── Schema builder ────────────────────────────────────────────────────────────

def _build_index_schema(index_name: str) -> SearchIndex:
    """
    Build the SearchIndex definition with HNSW vector search and semantic ranking.
    """
    # Note: in azure-search-documents 11.4+, `retrievable` was removed.
    # All fields are retrievable by default; use hidden=True to suppress.
    fields = [
        SearchField(
            name="id",
            type=SearchFieldDataType.String,
            key=True,
            filterable=True,
        ),
        SearchField(
            name="title",
            type=SearchFieldDataType.String,
            searchable=True,
            analyzer_name="en.microsoft",
        ),
        SearchField(
            name="content",
            type=SearchFieldDataType.String,
            searchable=True,
            analyzer_name="en.microsoft",
        ),
        SearchField(
            name="document_type",
            type=SearchFieldDataType.String,
            filterable=True,
            facetable=True,
        ),
        SearchField(
            name="source_file",
            type=SearchFieldDataType.String,
            filterable=True,
        ),
        SearchField(
            name="chunk_index",
            type=SearchFieldDataType.Int32,
            filterable=True,
            sortable=True,
        ),
        # Vector field — hidden from search results to save bandwidth
        SearchField(
            name="content_vector",
            type=SearchFieldDataType.Collection(SearchFieldDataType.Single),
            searchable=True,
            hidden=True,
            vector_search_dimensions=_VECTOR_DIMS,
            vector_search_profile_name="vector-profile",
        ),
    ]

    vector_search = VectorSearch(
        algorithms=[
            HnswAlgorithmConfiguration(name="hnsw-config"),
        ],
        profiles=[
            VectorSearchProfile(
                name="vector-profile",
                algorithm_configuration_name="hnsw-config",
            )
        ],
    )

    semantic_search = SemanticSearch(
        default_configuration_name="insighthub-semantic",
        configurations=[
            SemanticConfiguration(
                name="insighthub-semantic",
                prioritized_fields=SemanticPrioritizedFields(
                    title_field=SemanticField(field_name="title"),
                    content_fields=[SemanticField(field_name="content")],
                    keywords_fields=[SemanticField(field_name="document_type")],
                ),
            )
        ],
    )

    return SearchIndex(
        name=index_name,
        fields=fields,
        vector_search=vector_search,
        semantic_search=semantic_search,
    )


# ── Index management ──────────────────────────────────────────────────────────

def create_or_recreate_index(cfg, force_recreate: bool = True) -> None:
    """
    Create the index.  If force_recreate=True, delete the existing index first.
    """
    credential = AzureKeyCredential(cfg.azure_search_key)
    index_client = SearchIndexClient(
        endpoint=cfg.azure_search_endpoint,
        credential=credential,
    )

    if force_recreate:
        try:
            index_client.delete_index(cfg.azure_search_index)
            log.info("Deleted existing index '%s'.", cfg.azure_search_index)
        except ResourceNotFoundError:
            pass  # Index did not exist yet; nothing to delete

    schema = _build_index_schema(cfg.azure_search_index)
    index_client.create_or_update_index(schema)
    log.info("Index '%s' created / updated.", cfg.azure_search_index)


# ── Blob upload (optional archival step) ──────────────────────────────────────

def upload_docs_to_blob(docs_dir: Path, cfg) -> int:
    """
    Upload all *.md files in docs_dir to Azure Blob Storage under
    cfg.storage_docs_prefix.  Returns number of files uploaded.

    This is optional archival.  The index is built from local files;
    blob storage provides a durable backup and allows ADF to pick them up.
    """
    if not cfg.storage_account_name or not cfg.storage_account_key:
        log.info("Blob credentials not set — skipping blob upload.")
        return 0

    try:
        from azure.storage.blob import BlobServiceClient
    except ImportError:
        log.warning(
            "azure-storage-blob not installed — skipping blob upload. "
            "Run: pip install azure-storage-blob"
        )
        return 0

    account_url = f"https://{cfg.storage_account_name}.blob.core.windows.net"
    service = BlobServiceClient(
        account_url=account_url,
        credential=cfg.storage_account_key,
    )
    container = service.get_container_client(cfg.storage_container)

    count = 0
    for md_file in sorted(docs_dir.glob("*.md")):
        blob_name = cfg.storage_docs_prefix + md_file.name
        blob = container.get_blob_client(blob_name)
        with open(md_file, "rb") as fh:
            blob.upload_blob(fh, overwrite=True)
        log.info("  Uploaded %s → %s/%s", md_file.name, cfg.storage_container, blob_name)
        count += 1

    return count


# ── Chunk ID ──────────────────────────────────────────────────────────────────

def _make_chunk_id(source_file: str, chunk_index: int) -> str:
    """
    Deterministic, URL-safe ID for a document chunk.
    Uses MD5 of 'source_file::chunk_index'.
    """
    raw = f"{source_file}::{chunk_index}"
    return hashlib.md5(raw.encode("utf-8")).hexdigest()


# ── Main indexer ──────────────────────────────────────────────────────────────

def run_indexer(docs_dir: Path, force_recreate: bool = True) -> int:
    """
    Full indexer pipeline:
      1. Upload docs to blob storage (optional).
      2. Create / recreate the Azure AI Search index.
      3. Load and chunk all documents from docs_dir.
      4. Generate embeddings for every chunk (batched).
      5. Upload chunks with vectors to the index.

    Args:
        docs_dir: Directory containing *.md source documents.
        force_recreate: If True, delete and recreate the index from scratch.

    Returns:
        Total number of document chunks successfully indexed.

    Raises:
        RuntimeError: If required Azure credentials are missing.
    """
    cfg = get_rag_config()

    # Validate required credentials
    missing = []
    if not cfg.azure_search_endpoint:
        missing.append("AZURE_SEARCH_ENDPOINT")
    if not cfg.azure_search_key:
        missing.append("AZURE_SEARCH_KEY")
    if not cfg.azure_openai_endpoint:
        missing.append("AZURE_OPENAI_ENDPOINT")
    if not cfg.azure_openai_key:
        missing.append("AZURE_OPENAI_KEY")
    if missing:
        raise RuntimeError(
            f"Missing required environment variables: {', '.join(missing)}. "
            "Ensure they are set in your .env file."
        )

    # Step 1: Optional blob archival upload
    log.info("─── Step 1: Blob upload (archival) ───────────────────────────")
    uploaded = upload_docs_to_blob(docs_dir, cfg)
    if uploaded:
        log.info("  %d documents uploaded to blob storage.", uploaded)

    # Step 2: Index creation
    log.info("─── Step 2: Create / update index ────────────────────────────")
    create_or_recreate_index(cfg, force_recreate=force_recreate)

    # Step 3: Load and chunk documents
    log.info("─── Step 3: Load and chunk documents ─────────────────────────")
    chunks = load_all_documents(
        docs_dir,
        chunk_size=cfg.chunk_size_words,
        overlap=cfg.chunk_overlap_words,
    )
    source_files = {c["source_file"] for c in chunks}
    log.info(
        "  %d chunks from %d source documents.",
        len(chunks), len(source_files),
    )

    # Step 4: Generate embeddings (batched)
    log.info("─── Step 4: Generate embeddings ──────────────────────────────")
    embedder = EmbeddingClient()
    texts = [c["content"] for c in chunks]
    embeddings = embedder.embed_batch(texts)
    log.info("  %d embeddings generated.", len(embeddings))

    # Step 5: Build and upload documents to the index
    log.info("─── Step 5: Upload to Azure AI Search ────────────────────────")
    documents = [
        {
            "id": _make_chunk_id(chunk["source_file"], chunk["chunk_index"]),
            "title": chunk["title"],
            "content": chunk["content"],
            "document_type": chunk["document_type"],
            "source_file": chunk["source_file"],
            "chunk_index": chunk["chunk_index"],
            "content_vector": embedding,
        }
        for chunk, embedding in zip(chunks, embeddings)
    ]

    credential = AzureKeyCredential(cfg.azure_search_key)
    search_client = SearchClient(
        endpoint=cfg.azure_search_endpoint,
        index_name=cfg.azure_search_index,
        credential=credential,
    )

    batch_size = 50
    total_indexed = 0
    num_batches = (len(documents) + batch_size - 1) // batch_size

    for i in range(0, len(documents), batch_size):
        batch = documents[i: i + batch_size]
        batch_num = i // batch_size + 1
        try:
            results = search_client.upload_documents(documents=batch)
            succeeded = sum(1 for r in results if r.succeeded)
            failed = len(batch) - succeeded
            total_indexed += succeeded
            log.info(
                "  Batch %d/%d: %d succeeded, %d failed.",
                batch_num, num_batches, succeeded, failed,
            )
            if failed:
                failed_ids = [
                    r.key for r in results if not r.succeeded
                ]
                log.warning("  Failed document IDs: %s", failed_ids[:10])
        except HttpResponseError as exc:
            log.error(
                "  Batch %d/%d upload error: %s",
                batch_num, num_batches, exc,
            )

    log.info(
        "─── Indexing complete: %d/%d chunks indexed into '%s' ────",
        total_indexed, len(documents), cfg.azure_search_index,
    )
    return total_indexed
