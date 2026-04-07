"""Tests for wiki schema definition and article type models."""

from __future__ import annotations

from assistonauts.models.schema import (
    ArticleType,
    FrontmatterSpec,
    SectionSpec,
    WikiSchema,
    get_default_schema,
)


class TestArticleType:
    """Test article type enumeration."""

    def test_all_types_defined(self) -> None:
        assert set(ArticleType) == {
            ArticleType.CONCEPT,
            ArticleType.ENTITY,
            ArticleType.LOG,
            ArticleType.EXPLORATION,
        }

    def test_type_values_are_lowercase(self) -> None:
        for t in ArticleType:
            assert t.value == t.value.lower()


class TestFrontmatterSpec:
    """Test frontmatter field specification."""

    def test_required_fields(self) -> None:
        spec = FrontmatterSpec(name="title", required=True)
        assert spec.name == "title"
        assert spec.required is True
        assert spec.default is None

    def test_optional_with_default(self) -> None:
        spec = FrontmatterSpec(name="status", required=False, default="draft")
        assert spec.default == "draft"


class TestSectionSpec:
    """Test article section specification."""

    def test_section_fields(self) -> None:
        sec = SectionSpec(
            heading="Overview",
            required=True,
            guidance="Summarize the core concept in 2-3 sentences.",
        )
        assert sec.heading == "Overview"
        assert sec.required is True
        assert sec.guidance == "Summarize the core concept in 2-3 sentences."

    def test_optional_section(self) -> None:
        sec = SectionSpec(heading="See Also", required=False, guidance="")
        assert sec.required is False


class TestWikiSchema:
    """Test the full wiki schema."""

    def test_default_schema_has_all_types(self) -> None:
        schema = get_default_schema()
        for article_type in ArticleType:
            assert article_type in schema.article_types

    def test_concept_has_required_frontmatter(self) -> None:
        schema = get_default_schema()
        template = schema.article_types[ArticleType.CONCEPT]
        field_names = {f.name for f in template.frontmatter}
        assert "title" in field_names
        assert "type" in field_names
        assert "sources" in field_names
        assert "created_at" in field_names

    def test_concept_has_sections(self) -> None:
        schema = get_default_schema()
        template = schema.article_types[ArticleType.CONCEPT]
        headings = [s.heading for s in template.sections]
        assert "Overview" in headings
        assert "Key Concepts" in headings
        assert "Sources" in headings

    def test_entity_has_sections(self) -> None:
        schema = get_default_schema()
        template = schema.article_types[ArticleType.ENTITY]
        headings = [s.heading for s in template.sections]
        assert "Overview" in headings
        assert "Background" in headings
        assert "Sources" in headings

    def test_log_has_sections(self) -> None:
        schema = get_default_schema()
        template = schema.article_types[ArticleType.LOG]
        headings = [s.heading for s in template.sections]
        assert "Summary" in headings
        assert "Timeline" in headings
        assert "Sources" in headings

    def test_exploration_has_sections(self) -> None:
        schema = get_default_schema()
        template = schema.article_types[ArticleType.EXPLORATION]
        headings = [s.heading for s in template.sections]
        assert "Question" in headings
        assert "Analysis" in headings
        assert "Sources" in headings

    def test_all_types_have_sources_section(self) -> None:
        schema = get_default_schema()
        for article_type, template in schema.article_types.items():
            headings = [s.heading for s in template.sections]
            assert "Sources" in headings, f"{article_type.value} missing Sources section"

    def test_naming_convention(self) -> None:
        schema = get_default_schema()
        assert schema.naming.slug_separator == "-"
        assert schema.naming.max_slug_length > 0

    def test_backlink_format(self) -> None:
        schema = get_default_schema()
        assert schema.backlink_format is not None
        assert "[[" in schema.backlink_format or "[" in schema.backlink_format

    def test_get_template_for_type(self) -> None:
        schema = get_default_schema()
        template = schema.get_template(ArticleType.CONCEPT)
        assert template is not None
        assert len(template.sections) > 0

    def test_required_frontmatter_for_all_types(self) -> None:
        schema = get_default_schema()
        for article_type, template in schema.article_types.items():
            required = [f for f in template.frontmatter if f.required]
            required_names = {f.name for f in required}
            assert "title" in required_names, f"{article_type.value} missing required 'title'"
            assert "type" in required_names, f"{article_type.value} missing required 'type'"
