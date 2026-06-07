#!/usr/bin/env python
"""
ai-search/run_indexer.py

Entry point to build or rebuild the InsightHub Azure AI Search index.

What it does:
  1. Uploads all *.md documents in ai-search/documents/ to Azure Blob Storage
     (optional — only if STORAGE_ACCOUNT_NAME and STORAGE_ACCOUNT_KEY are set).
  2. Creates (or recreates) the Azure AI Search index with:
     - Full-text searchable fields (title, content, document_type)
     - 1536-dimensional HNSW vector field (content_vector)
     - Semantic ranking configuration
  3. Chunks every document (~300 words, 60-word overlap).
  4. Generates embeddings for each chunk via Azure OpenAI.
  5. Uploads all chunks with their vectors to the index.

Prerequisites in .env:
  AZURE_SEARCH_ENDPOINT      — e.g. https://your-search.search.windows.net
  AZURE_SEARCH_KEY           — Admin API key
  AZURE_OPENAI_ENDPOINT      — e.g. https://your-openai.openai.azure.com/
  AZURE_OPENAI_KEY           — Azure OpenAI API key
  AZURE_OPENAI_EMBEDDING_DEPLOYMENT — deployed model name (default: text-embedding-ada-002)

Optional in .env:
  STORAGE_ACCOUNT_NAME       — for blob archival upload
  STORAGE_ACCOUNT_KEY
  STORAGE_CONTAINER          — default: insighthub
  AZURE_SEARCH_INDEX         — default: insighthub-docs

Usage (run from the project root):
  python ai-search/run_indexer.py
  python ai-search/run_indexer.py --no-recreate   # append without deleting index
"""
import argparse
import logging
import sys
from pathlib import Path

# Add rag-pipeline package to the Python path
_PIPELINE_DIR = Path(__file__).resolve().parent / "rag-pipeline"
sys.path.insert(0, str(_PIPELINE_DIR))

from indexer import run_indexer  # noqa: E402  (must come after sys.path update)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger(__name__)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Build the InsightHub Azure AI Search knowledge index.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--no-recreate",
        action="store_true",
        help=(
            "Append to the existing index instead of deleting and recreating it. "
            "Use this for incremental updates when documents are added or changed."
        ),
    )
    args = parser.parse_args()

    docs_dir = Path(__file__).resolve().parent / "documents"

    if not docs_dir.is_dir():
        log.error("Documents directory not found: %s", docs_dir)
        sys.exit(1)

    md_files = [f for f in docs_dir.glob("*.md") if f.name.lower() != "readme.md"]
    if not md_files:
        log.error("No markdown documents found in %s", docs_dir)
        sys.exit(1)

    log.info("InsightHub AI Search Indexer")
    log.info("  Documents directory : %s", docs_dir)
    log.info("  Documents found     : %d", len(md_files))
    log.info("  Force recreate index: %s", not args.no_recreate)
    log.info("")

    try:
        total = run_indexer(
            docs_dir=docs_dir,
            force_recreate=not args.no_recreate,
        )
    except RuntimeError as exc:
        log.error("Indexer failed: %s", exc)
        sys.exit(1)
    except KeyboardInterrupt:
        log.warning("Indexer interrupted by user.")
        sys.exit(1)

    log.info("")
    log.info("Done. %d chunks successfully indexed.", total)
    log.info(
        "Test the index: python -c \""
        "import sys; sys.path.insert(0, 'ai-search/rag-pipeline'); "
        "from searcher import HybridSearcher; "
        "s = HybridSearcher(); "
        "print(s.search('What is the annual leave entitlement?'))\""
    )


if __name__ == "__main__":
    main()
