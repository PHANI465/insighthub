"""
ai-search/rag-pipeline/chunker.py

Loads markdown documents and splits them into overlapping word-window chunks.
No external dependencies beyond the standard library.
"""
import re
from pathlib import Path
from typing import Dict, List, Tuple

# Maps filename prefix → human-readable document type stored in the index
_PREFIX_TO_TYPE: Dict[str, str] = {
    "hr_": "HR Policy",
    "it_": "IT Policy",
    "finance_": "Finance Policy",
    "sales_": "Sales Report",
    "product_": "Product",
    "customer_": "Customer Service",
    "compliance_": "Compliance",
    "operations_": "Operations",
}

_NULLISH = frozenset({"nan", "none", "n/a", "na", ""})


def infer_document_type(filename: str) -> str:
    """Infer document type from a lowercase filename prefix."""
    name = filename.lower()
    for prefix, doc_type in _PREFIX_TO_TYPE.items():
        if name.startswith(prefix):
            return doc_type
    return "Internal Document"


def extract_title(text: str, fallback_stem: str) -> str:
    """
    Extract the first H1 heading from a markdown document.
    Falls back to the filename stem, title-cased.
    """
    match = re.search(r"^#\s+(.+)$", text, re.MULTILINE)
    if match:
        return match.group(1).strip()
    return fallback_stem.replace("_", " ").title()


def chunk_text(text: str, chunk_size: int = 300, overlap: int = 60) -> List[str]:
    """
    Split text into overlapping word-window chunks.

    Strategy:
      1. Split on paragraph boundaries (two or more newlines).
      2. Accumulate words until chunk_size is reached.
      3. Step back `overlap` words to begin the next chunk, preserving context.

    Args:
        text: Raw document text.
        chunk_size: Target number of words per chunk.
        overlap: Number of words to repeat at the start of each new chunk.

    Returns:
        List of non-empty text chunks (strings of words joined by spaces).
    """
    # Flatten paragraphs into a single word list
    paragraphs = [p.strip() for p in re.split(r"\n{2,}", text) if p.strip()]
    words: List[str] = []
    for para in paragraphs:
        words.extend(para.split())

    if not words:
        return []

    chunks: List[str] = []
    start = 0
    while start < len(words):
        end = min(start + chunk_size, len(words))
        chunks.append(" ".join(words[start:end]))
        if end == len(words):
            break
        # Step forward by (chunk_size - overlap) to create the overlap window
        start = max(start + 1, end - overlap)

    return [c for c in chunks if c.strip()]


def load_document(path: Path) -> Tuple[str, str, str]:
    """
    Read a markdown file.

    Returns:
        (title, document_type, full_text)
    """
    text = path.read_text(encoding="utf-8")
    title = extract_title(text, path.stem)
    doc_type = infer_document_type(path.name)
    return title, doc_type, text


def load_all_documents(docs_dir: Path, chunk_size: int = 300, overlap: int = 60) -> List[dict]:
    """
    Load and chunk all *.md files in docs_dir (skipping README.md).

    Returns:
        List of dicts, each representing one chunk:
        {
            "source_file": str,
            "title": str,
            "document_type": str,
            "chunk_index": int,
            "content": str,
        }
    """
    docs_dir = Path(docs_dir)
    if not docs_dir.is_dir():
        raise FileNotFoundError(f"Documents directory not found: {docs_dir}")

    results: List[dict] = []
    md_files = sorted(f for f in docs_dir.glob("*.md") if f.name.lower() != "readme.md")

    if not md_files:
        raise ValueError(f"No markdown documents found in {docs_dir}")

    for md_file in md_files:
        title, doc_type, text = load_document(md_file)
        chunks = chunk_text(text, chunk_size=chunk_size, overlap=overlap)
        for idx, chunk in enumerate(chunks):
            results.append({
                "source_file": md_file.name,
                "title": title,
                "document_type": doc_type,
                "chunk_index": idx,
                "content": chunk,
            })

    return results
