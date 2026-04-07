"""Tests for Scout toolkit functions."""

from pathlib import Path
from unittest.mock import MagicMock, patch

from assistonauts.tools.scout import (
    check_dedup,
    check_relevance_keywords,
    clip_web,
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


class TestCheckDedup:
    """Test near-duplicate detection."""

    def test_identical_content_matches(self) -> None:
        """Identical content returns high similarity."""
        content = "This is a test document about machine learning."
        existing = {"raw/doc1.md": content}
        matches = check_dedup(content, existing)
        assert len(matches) == 1
        assert matches[0].similarity == 1.0

    def test_similar_content_matches(self) -> None:
        """Very similar content is detected as near-duplicate."""
        base = (
            "Machine learning approaches to cryptocurrency price prediction "
            "using deep neural networks and reinforcement learning techniques "
            "for automated trading systems."
        )
        # Same text with one word changed — high shingle overlap
        variant = (
            "Machine learning approaches to cryptocurrency price prediction "
            "using deep neural networks and reinforcement learning methods "
            "for automated trading systems."
        )
        existing = {"raw/doc1.md": base}
        matches = check_dedup(variant, existing)
        assert len(matches) >= 1
        assert matches[0].similarity >= 0.8

    def test_different_content_no_match(self) -> None:
        """Completely different content has no matches."""
        content = "The weather today is sunny and warm."
        existing = {
            "raw/doc1.md": "Quantum physics explains subatomic particle behavior."
        }
        matches = check_dedup(content, existing)
        assert len(matches) == 0

    def test_empty_content(self) -> None:
        """Empty content returns no matches."""
        matches = check_dedup("", {"raw/doc.md": "some content"})
        assert len(matches) == 0

    def test_empty_existing(self) -> None:
        """Empty existing dict returns no matches."""
        matches = check_dedup("some content", {})
        assert len(matches) == 0

    def test_match_returns_key(self) -> None:
        """Match result contains the key of the matching entry."""
        content = "Identical content here for testing dedup detection."
        existing = {"raw/papers/test.md": content}
        matches = check_dedup(content, existing)
        assert matches[0].key == "raw/papers/test.md"


class TestClipWeb:
    """Test web clipping (with mocked network)."""

    @patch("assistonauts.tools.scout.urllib.request.urlretrieve")
    def test_clip_web_returns_markdown(
        self, mock_urlretrieve: MagicMock, tmp_path: Path
    ) -> None:
        """clip_web fetches a URL and returns markdown content."""

        # Write a fake HTML file where urlretrieve would save it
        def fake_retrieve(url: str, dest: str) -> None:
            Path(dest).write_text(
                "<html><body><h1>Title</h1><p>Content here.</p></body></html>"
            )

        mock_urlretrieve.side_effect = fake_retrieve

        content, assets = clip_web("https://example.com/article", tmp_path)

        assert isinstance(content, str)
        assert len(content) > 0
        assert isinstance(assets, list)
        mock_urlretrieve.assert_called_once()

    @patch("assistonauts.tools.scout.urllib.request.urlretrieve")
    def test_clip_web_cleans_up_temp_file(
        self, mock_urlretrieve: MagicMock, tmp_path: Path
    ) -> None:
        """clip_web removes the temp HTML file after conversion."""

        def fake_retrieve(url: str, dest: str) -> None:
            Path(dest).write_text("<html><body>Test</body></html>")

        mock_urlretrieve.side_effect = fake_retrieve

        clip_web("https://example.com/page", tmp_path)

        # No _web_*.html files should remain
        html_files = list(tmp_path.glob("_web_*.html"))
        assert len(html_files) == 0

    @patch("assistonauts.tools.scout.urllib.request.urlretrieve")
    def test_clip_web_creates_output_dir(
        self, mock_urlretrieve: MagicMock, tmp_path: Path
    ) -> None:
        """clip_web creates the output directory if it doesn't exist."""
        output = tmp_path / "new_dir"

        def fake_retrieve(url: str, dest: str) -> None:
            Path(dest).write_text("<html><body>Test</body></html>")

        mock_urlretrieve.side_effect = fake_retrieve

        clip_web("https://example.com", output)

        assert output.is_dir()
