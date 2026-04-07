"""Scout agent toolkit — deterministic utility functions.

All functions are pure/deterministic (no LLM calls) and independently testable.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path

from assistonauts.cache.content import hash_content as _hash_content


def hash_content(path: Path) -> str:
    """Return SHA-256 hex digest of a file's contents."""
    return _hash_content(path)


def check_relevance_keywords(text: str, keywords: list[str]) -> float:
    """Score text relevance against a keyword list.

    Returns a float between 0.0 and 1.0 representing the fraction
    of keywords found in the text (case-insensitive).
    Returns 1.0 if keyword list is empty (no filtering).
    """
    if not keywords:
        return 1.0

    text_lower = text.lower()
    matches = sum(1 for kw in keywords if kw.lower() in text_lower)
    return matches / len(keywords)


def convert_text_file(path: Path) -> str:
    """Read a plain text or markdown file and return its content.

    For .txt and .md files, this is a simple read. More complex formats
    (PDF, HTML, DOCX) use markitdown and are handled by convert_document().
    """
    return path.read_text(encoding="utf-8")


def convert_document(path: Path) -> str:
    """Convert a document (PDF, HTML, DOCX) to markdown via markitdown.

    Falls back to plain text read for .txt/.md files.
    """
    suffix = path.suffix.lower()
    if suffix in (".txt", ".md", ".markdown"):
        return convert_text_file(path)

    from markitdown import MarkItDown

    converter = MarkItDown()
    result = converter.convert(str(path))
    return result.text_content


def clip_web(url: str, output_dir: Path) -> tuple[str, list[Path]]:
    """Fetch a URL, extract content as markdown, download assets.

    Returns a tuple of (markdown_content, list_of_downloaded_asset_paths).
    """
    import urllib.request

    from markitdown import MarkItDown

    # Download the page to a temp file
    output_dir.mkdir(parents=True, exist_ok=True)
    url_hash = hashlib.sha256(url.encode()).hexdigest()[:12]
    temp_html = output_dir / f"_web_{url_hash}.html"

    urllib.request.urlretrieve(url, temp_html)

    # Convert to markdown
    converter = MarkItDown()
    result = converter.convert(str(temp_html))

    # Clean up temp file
    temp_html.unlink(missing_ok=True)

    return result.text_content, []


@dataclass
class DedupMatch:
    """A near-duplicate match result."""

    key: str
    similarity: float


def check_dedup(content: str, existing_hashes: dict[str, str]) -> list[DedupMatch]:
    """Check for near-duplicate content using simple n-gram similarity.

    Compares the content's shingle set against existing entries.
    Returns a list of matches above the similarity threshold (0.8).

    Uses a simple Jaccard similarity on 3-gram shingle sets as a
    lightweight approximation of simhash/minhash. Sufficient for
    v1 deduplication; can be upgraded to proper minhash later.
    """
    threshold = 0.8
    content_shingles = _shingle(content)

    if not content_shingles:
        return []

    matches: list[DedupMatch] = []
    for key, existing_text in existing_hashes.items():
        existing_shingles = _shingle(existing_text)
        if not existing_shingles:
            continue
        similarity = _jaccard(content_shingles, existing_shingles)
        if similarity >= threshold:
            matches.append(DedupMatch(key=key, similarity=similarity))

    return sorted(matches, key=lambda m: m.similarity, reverse=True)


def _shingle(text: str, n: int = 3) -> set[str]:
    """Generate n-gram character shingles from text."""
    text = text.lower().strip()
    if len(text) < n:
        return {text} if text else set()
    return {text[i : i + n] for i in range(len(text) - n + 1)}


def _jaccard(a: set[str], b: set[str]) -> float:
    """Jaccard similarity between two sets."""
    if not a and not b:
        return 1.0
    intersection = len(a & b)
    union = len(a | b)
    return intersection / union if union > 0 else 0.0
