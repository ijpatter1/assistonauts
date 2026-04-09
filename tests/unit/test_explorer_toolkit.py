"""Tests for Explorer toolkit — citation formatter, context budget, output renderer."""

from __future__ import annotations

from assistonauts.tools.explorer import (
    Citation,
    calculate_context_budget,
    format_citation,
    format_citations_block,
    render_answer_chart_data,
    render_answer_markdown,
    render_answer_marp,
)

# --- Citation formatter tests ---


class TestFormatCitation:
    def test_basic_citation(self) -> None:
        citation = Citation(
            title="Neural Networks", path="wiki/concept/neural-networks.md"
        )
        result = format_citation(citation)
        assert "Neural Networks" in result
        assert "wiki/concept/neural-networks.md" in result

    def test_citation_with_section(self) -> None:
        citation = Citation(
            title="Neural Networks",
            path="wiki/concept/neural-networks.md",
            section="Key Concepts",
        )
        result = format_citation(citation)
        assert "Neural Networks" in result
        assert "Key Concepts" in result

    def test_citation_renders_as_wiki_link(self) -> None:
        citation = Citation(
            title="Neural Networks", path="wiki/concept/neural-networks.md"
        )
        result = format_citation(citation)
        # Should use markdown link format
        assert "[" in result and "]" in result

    def test_citation_with_relevance(self) -> None:
        citation = Citation(
            title="Neural Networks",
            path="wiki/concept/neural-networks.md",
            relevance="high",
        )
        result = format_citation(citation)
        assert "Neural Networks" in result


class TestFormatCitationsBlock:
    def test_empty_citations(self) -> None:
        result = format_citations_block([])
        assert result == ""

    def test_single_citation(self) -> None:
        citations = [Citation(title="Article A", path="wiki/concept/a.md")]
        result = format_citations_block(citations)
        assert "Article A" in result
        assert "Sources" in result

    def test_multiple_citations(self) -> None:
        citations = [
            Citation(title="Article A", path="wiki/concept/a.md"),
            Citation(title="Article B", path="wiki/entity/b.md"),
            Citation(title="Article C", path="wiki/log/c.md"),
        ]
        result = format_citations_block(citations)
        assert "Article A" in result
        assert "Article B" in result
        assert "Article C" in result

    def test_citations_are_numbered(self) -> None:
        citations = [
            Citation(title="First", path="wiki/concept/first.md"),
            Citation(title="Second", path="wiki/concept/second.md"),
        ]
        result = format_citations_block(citations)
        assert "1." in result or "[1]" in result
        assert "2." in result or "[2]" in result

    def test_deduplicates_same_path(self) -> None:
        citations = [
            Citation(title="Same Article", path="wiki/concept/same.md"),
            Citation(
                title="Same Article", path="wiki/concept/same.md", section="Details"
            ),
        ]
        result = format_citations_block(citations)
        # Should only list the article once
        lines_with_same = [
            line for line in result.splitlines() if "Same Article" in line
        ]
        assert len(lines_with_same) == 1


# --- Context budget calculator tests ---


class TestCalculateContextBudget:
    def test_empty_articles(self) -> None:
        budget = calculate_context_budget([], max_tokens=4000)
        assert budget.included == []
        assert budget.excluded == []
        assert budget.total_tokens == 0

    def test_all_fit_within_budget(self) -> None:
        articles = [
            {"path": "a.md", "word_count": 100},
            {"path": "b.md", "word_count": 200},
        ]
        budget = calculate_context_budget(articles, max_tokens=4000)
        assert len(budget.included) == 2
        assert len(budget.excluded) == 0

    def test_excludes_articles_exceeding_budget(self) -> None:
        articles = [
            {"path": "a.md", "word_count": 2000},
            {"path": "b.md", "word_count": 2000},
            {"path": "c.md", "word_count": 2000},
        ]
        # ~1.3 tokens per word, so 2000 words ≈ 2600 tokens each
        budget = calculate_context_budget(articles, max_tokens=4000)
        assert len(budget.included) >= 1
        assert len(budget.excluded) >= 1
        assert budget.total_tokens <= 4000

    def test_preserves_order_by_relevance(self) -> None:
        articles = [
            {"path": "best.md", "word_count": 500, "hybrid_score": 0.9},
            {"path": "good.md", "word_count": 500, "hybrid_score": 0.7},
            {"path": "okay.md", "word_count": 500, "hybrid_score": 0.5},
        ]
        budget = calculate_context_budget(articles, max_tokens=10000)
        paths = [a["path"] for a in budget.included]
        assert paths[0] == "best.md"

    def test_total_tokens_is_accurate(self) -> None:
        articles = [
            {"path": "a.md", "word_count": 100},
        ]
        budget = calculate_context_budget(articles, max_tokens=4000)
        # words_to_tokens uses ~1.3 ratio
        assert budget.total_tokens > 0
        assert budget.total_tokens == budget.token_estimate(100)

    def test_zero_max_tokens_excludes_all(self) -> None:
        articles = [{"path": "a.md", "word_count": 100}]
        budget = calculate_context_budget(articles, max_tokens=0)
        assert len(budget.included) == 0
        assert len(budget.excluded) == 1

    def test_respects_hybrid_score_ordering(self) -> None:
        """Higher-scored articles should be included first when budget is tight."""
        articles = [
            {"path": "low.md", "word_count": 1000, "hybrid_score": 0.2},
            {"path": "high.md", "word_count": 1000, "hybrid_score": 0.9},
        ]
        budget = calculate_context_budget(articles, max_tokens=2000)
        if len(budget.included) == 1:
            assert budget.included[0]["path"] == "high.md"


# --- Output renderer tests ---


class TestRenderAnswerMarkdown:
    def test_renders_answer_with_citations(self) -> None:
        citations = [
            Citation(title="Article A", path="wiki/concept/a.md"),
        ]
        result = render_answer_markdown("This is the answer.", citations)
        assert "This is the answer." in result
        assert "Article A" in result

    def test_answer_without_citations(self) -> None:
        result = render_answer_markdown("This is the answer.", [])
        assert "This is the answer." in result

    def test_answer_includes_sources_section(self) -> None:
        citations = [
            Citation(title="Source", path="wiki/concept/source.md"),
        ]
        result = render_answer_markdown("Answer text.", citations)
        assert "Sources" in result or "References" in result

    def test_renders_valid_markdown(self) -> None:
        citations = [
            Citation(title="A", path="wiki/concept/a.md"),
            Citation(title="B", path="wiki/entity/b.md"),
        ]
        result = render_answer_markdown("Some answer.", citations)
        # Should be parseable as markdown (no unclosed brackets)
        open_brackets = result.count("[")
        close_brackets = result.count("]")
        assert open_brackets == close_brackets

    def test_query_included_when_provided(self) -> None:
        result = render_answer_markdown(
            "Answer text.",
            [],
            query="What is machine learning?",
        )
        assert "What is machine learning?" in result


class TestRenderAnswerMarp:
    def test_marp_has_frontmatter(self) -> None:
        result = render_answer_marp("Answer.", [])
        assert "marp: true" in result

    def test_marp_has_title_slide(self) -> None:
        result = render_answer_marp("Answer.", [], query="What is ML?")
        assert "# What is ML?" in result

    def test_marp_has_slide_separators(self) -> None:
        result = render_answer_marp("Paragraph one.\n\nParagraph two.", [])
        assert result.count("---") >= 3  # frontmatter + slide breaks

    def test_marp_has_sources_slide(self) -> None:
        citations = [Citation(title="A", path="wiki/concept/a.md")]
        result = render_answer_marp("Answer.", citations)
        assert "# Sources" in result
        assert "A" in result

    def test_marp_deduplicates_citations(self) -> None:
        citations = [
            Citation(title="A", path="wiki/concept/a.md"),
            Citation(title="A", path="wiki/concept/a.md", section="Details"),
        ]
        result = render_answer_marp("Answer.", citations)
        source_lines = [line for line in result.splitlines() if line.startswith("- ")]
        assert len(source_lines) == 1


class TestRenderAnswerChartData:
    def test_empty_citations(self) -> None:
        data = render_answer_chart_data([])
        assert data["labels"] == []
        assert data["values"] == []

    def test_single_citation(self) -> None:
        citations = [Citation(title="Article A", path="wiki/concept/a.md")]
        data = render_answer_chart_data(citations)
        assert data["labels"] == ["Article A"]
        assert data["values"] == [1.0]

    def test_duplicate_citations_counted(self) -> None:
        citations = [
            Citation(title="A", path="wiki/concept/a.md"),
            Citation(title="A", path="wiki/concept/a.md", section="Details"),
            Citation(title="B", path="wiki/entity/b.md"),
        ]
        data = render_answer_chart_data(citations)
        assert "A" in data["labels"]
        assert "B" in data["labels"]
        idx_a = data["labels"].index("A")
        assert data["values"][idx_a] == 2.0
