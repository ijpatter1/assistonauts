"""Tests for Scout toolkit functions."""

from pathlib import Path

from assistonauts.tools.scout import (
    check_relevance_keywords,
    convert_text_file,
    hash_content,
)


class TestHashContent:
    """Test content hashing (Scout-level wrapper)."""

    def test_hash_returns_sha256_hex(self, tmp_path: Path) -> None:
        """Returns a 64-char hex string (SHA-256)."""
        f = tmp_path / "test.txt"
        f.write_text("hello")
        result = hash_content(f)
        assert isinstance(result, str)
        assert len(result) == 64

    def test_same_content_same_hash(self, tmp_path: Path) -> None:
        """Deterministic hashing."""
        f = tmp_path / "a.txt"
        f.write_text("same")
        assert hash_content(f) == hash_content(f)


class TestCheckRelevanceKeywords:
    """Test keyword-based relevance scoring."""

    def test_full_match(self) -> None:
        """All keywords present gives score of 1.0."""
        text = "Machine learning for BTC trading with regime detection"
        keywords = ["machine learning", "BTC", "trading"]
        score = check_relevance_keywords(text, keywords)
        assert score == 1.0

    def test_partial_match(self) -> None:
        """Some keywords present gives proportional score."""
        text = "Machine learning overview"
        keywords = ["machine learning", "BTC", "trading", "regime"]
        score = check_relevance_keywords(text, keywords)
        assert 0.0 < score < 1.0
        assert score == 0.25  # 1 of 4 keywords

    def test_no_match(self) -> None:
        """No keywords present gives score of 0.0."""
        text = "Cooking recipes for beginners"
        keywords = ["machine learning", "BTC", "trading"]
        score = check_relevance_keywords(text, keywords)
        assert score == 0.0

    def test_case_insensitive(self) -> None:
        """Keyword matching is case-insensitive."""
        text = "MACHINE LEARNING is great"
        keywords = ["machine learning"]
        score = check_relevance_keywords(text, keywords)
        assert score == 1.0

    def test_empty_keywords(self) -> None:
        """Empty keyword list returns 1.0 (no filter)."""
        text = "anything"
        score = check_relevance_keywords(text, [])
        assert score == 1.0


class TestConvertTextFile:
    """Test plain text/markdown file conversion."""

    def test_reads_text_file(self, tmp_path: Path) -> None:
        """Converts a plain text file to its content."""
        f = tmp_path / "notes.txt"
        f.write_text("# My Notes\n\nSome content here.")
        content = convert_text_file(f)
        assert "My Notes" in content
        assert "Some content here." in content

    def test_reads_markdown_file(self, tmp_path: Path) -> None:
        """Reads .md files as-is."""
        f = tmp_path / "doc.md"
        f.write_text("# Title\n\n- bullet one\n- bullet two")
        content = convert_text_file(f)
        assert "# Title" in content
        assert "- bullet one" in content
