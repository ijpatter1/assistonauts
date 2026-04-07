"""Scout agent toolkit — deterministic utility functions.

All functions are pure/deterministic (no LLM calls) and independently testable.
"""

from __future__ import annotations

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
