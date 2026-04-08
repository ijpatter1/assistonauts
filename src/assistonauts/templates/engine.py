"""Template engine — renders structured markdown scaffolds from wiki schema.

Given an article type and context (title, sources), produces a markdown
document with YAML frontmatter and section headings with guidance placeholders
for the LLM to fill in.
"""

from __future__ import annotations

from datetime import UTC, datetime

from assistonauts.models.schema import ArticleType, WikiSchema


def render_template(
    schema: WikiSchema,
    article_type: ArticleType,
    title: str,
    sources: list[str],
) -> str:
    """Render a wiki article template for the given type.

    Produces a markdown document with:
    - YAML frontmatter (title, type, sources, created_at, status)
    - H1 title
    - H2 sections from the schema template, with guidance as placeholders
    """
    template = schema.get_template(article_type)
    now = datetime.now(UTC).isoformat()

    # Build frontmatter
    sources_yaml = "\n".join(f"  - {s}" for s in sources)
    frontmatter = (
        "---\n"
        f"title: {title}\n"
        f"type: {article_type.value}\n"
        f"sources:\n{sources_yaml}\n"
        f"created_at: {now}\n"
        f"compiled_by: compiler\n"
        f"status: draft\n"
        "---\n"
    )

    # Build body
    parts: list[str] = [frontmatter, f"\n# {title}\n"]

    for section in template.sections:
        parts.append(f"\n## {section.heading}\n")
        if section.guidance:
            parts.append(f"\n<!-- {section.guidance} -->\n")

    return "\n".join(parts)
