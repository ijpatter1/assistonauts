"""Wiki schema definition — article types, templates, and naming conventions.

Defines the structural contracts for wiki articles: what frontmatter fields
are required, what sections each article type contains, and how articles
are named and linked.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class ArticleType(Enum):
    """Supported wiki article types."""

    CONCEPT = "concept"
    ENTITY = "entity"
    LOG = "log"
    EXPLORATION = "exploration"


@dataclass(frozen=True)
class FrontmatterSpec:
    """Specification for a single frontmatter field."""

    name: str
    required: bool = True
    default: str | None = None


@dataclass(frozen=True)
class SectionSpec:
    """Specification for a wiki article section."""

    heading: str
    required: bool = True
    guidance: str = ""


@dataclass(frozen=True)
class NamingConvention:
    """Rules for article file naming."""

    slug_separator: str = "-"
    max_slug_length: int = 80


@dataclass(frozen=True)
class ArticleTemplate:
    """Complete template for one article type."""

    article_type: ArticleType
    frontmatter: list[FrontmatterSpec]
    sections: list[SectionSpec]


@dataclass
class WikiSchema:
    """Full wiki schema: article templates, naming, and backlink format."""

    article_types: dict[ArticleType, ArticleTemplate] = field(default_factory=dict)
    naming: NamingConvention = field(default_factory=NamingConvention)
    backlink_format: str = "[{title}]({path})"

    def get_template(self, article_type: ArticleType) -> ArticleTemplate:
        """Get the template for a given article type."""
        return self.article_types[article_type]


# --- Shared frontmatter fields ---

_COMMON_FRONTMATTER = [
    FrontmatterSpec(name="title", required=True),
    FrontmatterSpec(name="type", required=True),
    FrontmatterSpec(name="sources", required=True),
    FrontmatterSpec(name="created_at", required=True),
    FrontmatterSpec(name="updated_at", required=False),
    FrontmatterSpec(name="compiled_by", required=False, default="compiler"),
    FrontmatterSpec(name="status", required=False, default="draft"),
    FrontmatterSpec(name="tags", required=False),
]

# --- Article type templates ---

_CONCEPT_TEMPLATE = ArticleTemplate(
    article_type=ArticleType.CONCEPT,
    frontmatter=_COMMON_FRONTMATTER,
    sections=[
        SectionSpec(
            heading="Overview",
            required=True,
            guidance="Summarize the core concept in 2-3 sentences.",
        ),
        SectionSpec(
            heading="Key Concepts",
            required=True,
            guidance="Break down the main ideas, principles, or components.",
        ),
        SectionSpec(
            heading="Details",
            required=False,
            guidance="In-depth explanation, methodology, or technical details.",
        ),
        SectionSpec(
            heading="Related Work",
            required=False,
            guidance="How this relates to other concepts in the knowledge base.",
        ),
        SectionSpec(
            heading="Sources",
            required=True,
            guidance="List all source materials with citations.",
        ),
    ],
)

_ENTITY_TEMPLATE = ArticleTemplate(
    article_type=ArticleType.ENTITY,
    frontmatter=_COMMON_FRONTMATTER,
    sections=[
        SectionSpec(
            heading="Overview",
            required=True,
            guidance="Brief description of this entity (person, org, tool, etc.).",
        ),
        SectionSpec(
            heading="Background",
            required=True,
            guidance="History, origin, or context for this entity.",
        ),
        SectionSpec(
            heading="Key Contributions",
            required=False,
            guidance="Notable work, products, or contributions.",
        ),
        SectionSpec(
            heading="Relationships",
            required=False,
            guidance="Connections to other entities or concepts.",
        ),
        SectionSpec(
            heading="Sources",
            required=True,
            guidance="List all source materials with citations.",
        ),
    ],
)

_LOG_TEMPLATE = ArticleTemplate(
    article_type=ArticleType.LOG,
    frontmatter=_COMMON_FRONTMATTER,
    sections=[
        SectionSpec(
            heading="Summary",
            required=True,
            guidance="Brief summary of the event or development.",
        ),
        SectionSpec(
            heading="Timeline",
            required=True,
            guidance="Chronological sequence of events.",
        ),
        SectionSpec(
            heading="Impact",
            required=False,
            guidance="Consequences, effects, or significance.",
        ),
        SectionSpec(
            heading="Sources",
            required=True,
            guidance="List all source materials with citations.",
        ),
    ],
)

_EXPLORATION_TEMPLATE = ArticleTemplate(
    article_type=ArticleType.EXPLORATION,
    frontmatter=_COMMON_FRONTMATTER,
    sections=[
        SectionSpec(
            heading="Question",
            required=True,
            guidance="The question or topic being explored.",
        ),
        SectionSpec(
            heading="Analysis",
            required=True,
            guidance="Detailed analysis drawing from knowledge base sources.",
        ),
        SectionSpec(
            heading="Findings",
            required=False,
            guidance="Key takeaways or conclusions.",
        ),
        SectionSpec(
            heading="Open Questions",
            required=False,
            guidance="Remaining unknowns or areas for further investigation.",
        ),
        SectionSpec(
            heading="Sources",
            required=True,
            guidance="List all source materials with citations.",
        ),
    ],
)


def get_default_schema() -> WikiSchema:
    """Return the default wiki schema with all article type templates."""
    return WikiSchema(
        article_types={
            ArticleType.CONCEPT: _CONCEPT_TEMPLATE,
            ArticleType.ENTITY: _ENTITY_TEMPLATE,
            ArticleType.LOG: _LOG_TEMPLATE,
            ArticleType.EXPLORATION: _EXPLORATION_TEMPLATE,
        },
        naming=NamingConvention(slug_separator="-", max_slug_length=80),
        backlink_format="[{title}]({path})",
    )
