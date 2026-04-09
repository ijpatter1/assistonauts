"""Explorer toolkit — citation formatting, context budget, output rendering.

All functions are deterministic (no LLM inference). They format citations,
calculate which articles fit within a token budget, and render answers
as markdown.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

# Approximate tokens-per-word ratio for English text
_TOKENS_PER_WORD = 1.3


@dataclass(frozen=True)
class Citation:
    """A reference to a wiki article used in an answer."""

    title: str
    path: str
    section: str | None = None
    relevance: str | None = None


@dataclass
class ContextBudget:
    """Result of context budget calculation."""

    included: list[dict[str, object]] = field(default_factory=list)
    excluded: list[dict[str, object]] = field(default_factory=list)
    total_tokens: int = 0

    @staticmethod
    def token_estimate(word_count: int) -> int:
        """Estimate token count from word count."""
        return math.ceil(word_count * _TOKENS_PER_WORD)


def format_citation(citation: Citation) -> str:
    """Format a single citation as a markdown link.

    Returns a markdown link like: [Title](path) or [Title § Section](path#section)
    """
    if citation.section:
        anchor = citation.section.lower().replace(" ", "-")
        return f"[{citation.title} § {citation.section}]({citation.path}#{anchor})"
    return f"[{citation.title}]({citation.path})"


def format_citations_block(citations: list[Citation]) -> str:
    """Format a list of citations as a numbered Sources block.

    Deduplicates citations by path. Returns empty string for empty list.
    """
    if not citations:
        return ""

    # Deduplicate by path, keeping first occurrence
    seen: set[str] = set()
    unique: list[Citation] = []
    for c in citations:
        if c.path not in seen:
            seen.add(c.path)
            unique.append(c)

    lines = ["## Sources", ""]
    for i, citation in enumerate(unique, 1):
        lines.append(f"{i}. {format_citation(citation)}")

    return "\n".join(lines)


def calculate_context_budget(
    articles: list[dict[str, object]],
    max_tokens: int,
) -> ContextBudget:
    """Calculate which articles fit within the token budget.

    Articles are sorted by hybrid_score (descending) before inclusion.
    Higher-relevance articles are included first.
    """
    if not articles:
        return ContextBudget()

    # Sort by relevance score (highest first)
    sorted_articles = sorted(
        articles,
        key=lambda a: float(a.get("hybrid_score", 0)),
        reverse=True,
    )

    budget = ContextBudget()
    running_tokens = 0

    for article in sorted_articles:
        word_count = int(article.get("word_count", 0))
        tokens = ContextBudget.token_estimate(word_count)

        if running_tokens + tokens <= max_tokens:
            budget.included.append(article)
            running_tokens += tokens
        else:
            budget.excluded.append(article)

    budget.total_tokens = running_tokens
    return budget


def render_answer_markdown(
    answer: str,
    citations: list[Citation],
    query: str | None = None,
) -> str:
    """Render an Explorer answer as formatted markdown.

    Combines the answer text with a query header (if provided)
    and a citations block.
    """
    parts: list[str] = []

    if query:
        parts.append(f"## {query}")
        parts.append("")

    parts.append(answer)

    citations_block = format_citations_block(citations)
    if citations_block:
        parts.append("")
        parts.append(citations_block)

    return "\n".join(parts)
