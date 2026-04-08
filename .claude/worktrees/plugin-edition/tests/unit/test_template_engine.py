"""Tests for the template engine."""

from __future__ import annotations

from assistonauts.models.schema import ArticleType, get_default_schema
from assistonauts.templates.engine import render_template


class TestRenderTemplate:
    """Test template rendering for article types."""

    def test_concept_template_has_all_sections(self) -> None:
        schema = get_default_schema()
        result = render_template(
            schema=schema,
            article_type=ArticleType.CONCEPT,
            title="Machine Learning",
            sources=["ml-intro.md"],
        )
        assert "## Overview" in result
        assert "## Key Concepts" in result
        assert "## Sources" in result

    def test_entity_template_has_all_sections(self) -> None:
        schema = get_default_schema()
        result = render_template(
            schema=schema,
            article_type=ArticleType.ENTITY,
            title="OpenAI",
            sources=["openai-article.md"],
        )
        assert "## Overview" in result
        assert "## Background" in result
        assert "## Sources" in result

    def test_log_template_has_all_sections(self) -> None:
        schema = get_default_schema()
        result = render_template(
            schema=schema,
            article_type=ArticleType.LOG,
            title="GPT-4 Release",
            sources=["gpt4-news.md"],
        )
        assert "## Summary" in result
        assert "## Timeline" in result
        assert "## Sources" in result

    def test_exploration_template_has_all_sections(self) -> None:
        schema = get_default_schema()
        result = render_template(
            schema=schema,
            article_type=ArticleType.EXPLORATION,
            title="How do transformers work?",
            sources=["transformers-paper.md"],
        )
        assert "## Question" in result
        assert "## Analysis" in result
        assert "## Sources" in result

    def test_frontmatter_present(self) -> None:
        schema = get_default_schema()
        result = render_template(
            schema=schema,
            article_type=ArticleType.CONCEPT,
            title="Neural Networks",
            sources=["nn-basics.md"],
        )
        assert result.startswith("---\n")
        assert "title: Neural Networks" in result
        assert "type: concept" in result
        assert "sources:" in result
        assert "  - nn-basics.md" in result

    def test_multiple_sources_in_frontmatter(self) -> None:
        schema = get_default_schema()
        result = render_template(
            schema=schema,
            article_type=ArticleType.CONCEPT,
            title="Test",
            sources=["a.md", "b.md", "c.md"],
        )
        assert "  - a.md" in result
        assert "  - b.md" in result
        assert "  - c.md" in result

    def test_section_guidance_as_placeholder(self) -> None:
        schema = get_default_schema()
        result = render_template(
            schema=schema,
            article_type=ArticleType.CONCEPT,
            title="Test",
            sources=["test.md"],
        )
        # Guidance text should appear as placeholder for LLM to fill
        assert "Summarize the core concept" in result

    def test_title_as_h1(self) -> None:
        schema = get_default_schema()
        result = render_template(
            schema=schema,
            article_type=ArticleType.CONCEPT,
            title="Deep Learning",
            sources=["dl.md"],
        )
        assert "# Deep Learning" in result

    def test_created_at_in_frontmatter(self) -> None:
        schema = get_default_schema()
        result = render_template(
            schema=schema,
            article_type=ArticleType.CONCEPT,
            title="Test",
            sources=["test.md"],
        )
        assert "created_at:" in result

    def test_status_defaults_to_draft(self) -> None:
        schema = get_default_schema()
        result = render_template(
            schema=schema,
            article_type=ArticleType.CONCEPT,
            title="Test",
            sources=["test.md"],
        )
        assert "status: draft" in result
