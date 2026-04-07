"""Tests for compiler toolkit functions."""

from __future__ import annotations

from assistonauts.tools.compiler import (
    ArticleStats,
    StructuredDiff,
    compute_stats,
    generate_diff,
)


class TestGenerateDiff:
    """Test structured diff generation."""

    def test_new_content_shows_all_added(self) -> None:
        diff = generate_diff("", "New content here.")
        assert diff.has_changes is True
        assert len(diff.added_sections) > 0 or diff.summary != ""

    def test_identical_content_no_changes(self) -> None:
        content = "# Title\n\nSome content."
        diff = generate_diff(content, content)
        assert diff.has_changes is False

    def test_added_section_detected(self) -> None:
        old = "# Title\n\n## Overview\n\nOld overview."
        new = "# Title\n\n## Overview\n\nOld overview.\n\n## New Section\n\nNew content."
        diff = generate_diff(old, new)
        assert diff.has_changes is True
        assert "New Section" in diff.added_sections

    def test_removed_section_detected(self) -> None:
        old = "# Title\n\n## Overview\n\nContent.\n\n## Removed\n\nGone."
        new = "# Title\n\n## Overview\n\nContent."
        diff = generate_diff(old, new)
        assert diff.has_changes is True
        assert "Removed" in diff.removed_sections

    def test_modified_section_detected(self) -> None:
        old = "# Title\n\n## Overview\n\nOld content."
        new = "# Title\n\n## Overview\n\nNew content."
        diff = generate_diff(old, new)
        assert diff.has_changes is True
        assert "Overview" in diff.modified_sections

    def test_summary_is_human_readable(self) -> None:
        old = "# Title\n\n## Overview\n\nOld."
        new = "# Title\n\n## Overview\n\nNew."
        diff = generate_diff(old, new)
        assert isinstance(diff.summary, str)
        assert len(diff.summary) > 0

    def test_diff_returns_structured_type(self) -> None:
        diff = generate_diff("a", "b")
        assert isinstance(diff, StructuredDiff)


class TestComputeStats:
    """Test article statistics computation."""

    def test_word_count(self) -> None:
        content = "one two three four five"
        stats = compute_stats(content)
        assert stats.word_count == 5

    def test_word_count_with_frontmatter(self) -> None:
        content = "---\ntitle: Test\ntype: concept\n---\n\none two three"
        stats = compute_stats(content)
        # Frontmatter should be excluded from word count
        assert stats.word_count == 3

    def test_reading_time_short(self) -> None:
        content = " ".join(["word"] * 200)
        stats = compute_stats(content)
        assert stats.reading_time_minutes == 1

    def test_reading_time_long(self) -> None:
        content = " ".join(["word"] * 600)
        stats = compute_stats(content)
        assert stats.reading_time_minutes == 3

    def test_reading_time_minimum_one(self) -> None:
        content = "short"
        stats = compute_stats(content)
        assert stats.reading_time_minutes >= 1

    def test_source_count_from_frontmatter(self) -> None:
        content = (
            "---\n"
            "title: Test\n"
            "sources:\n"
            "  - source_a.md\n"
            "  - source_b.md\n"
            "  - source_c.md\n"
            "---\n\n"
            "Body text."
        )
        stats = compute_stats(content)
        assert stats.source_count == 3

    def test_source_count_zero_when_no_frontmatter(self) -> None:
        content = "Just some text without frontmatter."
        stats = compute_stats(content)
        assert stats.source_count == 0

    def test_empty_content(self) -> None:
        stats = compute_stats("")
        assert stats.word_count == 0
        assert stats.reading_time_minutes >= 1
        assert stats.source_count == 0

    def test_returns_stats_type(self) -> None:
        stats = compute_stats("hello world")
        assert isinstance(stats, ArticleStats)
