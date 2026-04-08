"""Compiler agent — transforms raw sources into structured wiki articles."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from assistonauts.agents.base import Agent, LLMClientProtocol
from assistonauts.cache.content import Manifest, ManifestEntry, hash_content
from assistonauts.models.schema import ArticleType, get_default_schema
from assistonauts.templates.engine import render_template
from assistonauts.tools.compiler import compute_stats, generate_diff

_COMPILER_SYSTEM_PROMPT = """\
You are Compiler, a knowledge compilation agent for the Assistonauts framework.
Your job is to transform raw source material into structured, well-written wiki
articles that conform to the expedition's schema and editorial standards.

You receive a markdown template with section headings and guidance comments.
Fill in each section with accurate, well-organized content drawn from the source
material. Maintain the heading structure exactly. Include citations to source
files where appropriate.

Guidelines:
- Write clear, concise prose. Prefer concrete statements over vague descriptions.
- Preserve all factual claims from the source. Do not invent information.
- Use the section guidance (HTML comments) to understand what each section needs.
- Include source citations in the Sources section.
- Output the complete article including frontmatter.
"""

_SUMMARY_SYSTEM_PROMPT = """\
You are a content summarizer for the Assistonauts knowledge base.
Given a wiki article, produce a concise content summary (2-4 sentences)
optimized for downstream triage. The summary should capture:
- The main topic and scope
- Key concepts or entities discussed
- What makes this article distinctive

Output ONLY the summary text, no formatting or labels.
"""


def _slugify(title: str, separator: str = "-", max_length: int = 80) -> str:
    """Convert a title to a URL-friendly slug."""
    slug = title.lower().strip()
    slug = re.sub(r"[^\w\s-]", "", slug)
    slug = re.sub(r"[\s_]+", separator, slug)
    slug = slug.strip(separator)
    return slug[:max_length]


@dataclass
class CompilationResult:
    """Result of a Compiler compile operation."""

    success: bool
    skipped: bool = False
    output_path: Path | None = None
    manifest_key: str = ""
    content_summary: str = ""
    message: str = ""


class CompilerAgent(Agent):
    """Compiler agent — compiles raw sources into wiki articles.

    Owns: wiki/
    Reads: raw/, index/
    """

    def __init__(
        self,
        llm_client: LLMClientProtocol,
        workspace_root: Path,
        expedition_scope: str = "",
    ) -> None:
        wiki_dir = workspace_root / "wiki"
        raw_dir = workspace_root / "raw"
        index_dir = workspace_root / "index"

        system_prompt = _COMPILER_SYSTEM_PROMPT
        if expedition_scope:
            system_prompt += (
                f"\n\nExpedition scope (use as editorial lens):\n{expedition_scope}\n"
            )

        super().__init__(
            role="compiler",
            system_prompt=system_prompt,
            llm_client=llm_client,
            owned_dirs=[wiki_dir],
            readable_dirs=[raw_dir, index_dir],
            toolkit={
                "compute_stats": compute_stats,
                "generate_diff": generate_diff,
            },
        )
        self._workspace_root = workspace_root
        self._manifest_path = index_dir / "manifest.json"
        self._schema = get_default_schema()

    def compile(
        self,
        source_path: Path,
        article_type: ArticleType,
        title: str,
    ) -> CompilationResult:
        """Compile a raw source into a wiki article.

        Pipeline:
        1. Check manifest — skip if source unchanged
        2. Read source content
        3. Render template scaffold
        4. Call LLM to fill sections
        5. Write article to wiki/
        6. Generate content summary
        7. Update manifest
        """
        source_path = source_path.resolve()
        manifest = Manifest(self._manifest_path)

        # Determine output location
        slug = _slugify(
            title,
            self._schema.naming.slug_separator,
            self._schema.naming.max_slug_length,
        )
        output_dir = self._workspace_root / "wiki" / article_type.value
        output_dir.mkdir(parents=True, exist_ok=True)
        output_path = output_dir / f"{slug}.md"
        manifest_key = f"wiki/{article_type.value}/{slug}.md"

        # Check if source has changed
        if not manifest.has_changed(source_path, manifest_key):
            return CompilationResult(
                success=True,
                skipped=True,
                output_path=output_path,
                manifest_key=manifest_key,
                message="Source unchanged, skipped.",
            )

        # Read source content
        source_content = self.read_file(source_path)

        # Check for existing article (recompilation)
        existing_content = ""
        if output_path.exists():
            existing_content = self.read_file(output_path)

        # Render template scaffold
        sources = [source_path.name]
        template = render_template(
            schema=self._schema,
            article_type=article_type,
            title=title,
            sources=sources,
        )

        # Build compilation prompt
        if existing_content:
            # For recompilation, provide the existing article and updated
            # source. The LLM reasons about what changed and updates the
            # article accordingly. We diff the article structures to give
            # the LLM a summary of the current article's shape.
            article_diff = generate_diff("", existing_content)
            compile_msg = (
                f"Recompile this wiki article based on updated source "
                f"material. The source has changed since the last "
                f"compilation.\n\n"
                f"Current article structure: "
                f"{article_diff.summary}\n\n"
                f"Current article:\n"
                f"```markdown\n{existing_content}\n```\n\n"
                f"Updated source material:\n"
                f"```markdown\n{source_content}\n```\n\n"
                f"Template structure to follow:\n"
                f"```markdown\n{template}\n```\n\n"
                f"Update the article to reflect the new source material. "
                f"Preserve existing content where it is still accurate. "
                f"Output the complete updated article including "
                f"frontmatter."
            )
        else:
            compile_msg = (
                f"Compile this source material into a wiki article.\n\n"
                f"Source material:\n```markdown\n{source_content}\n```\n\n"
                f"Template to fill:\n```markdown\n{template}\n```\n\n"
                f"Fill in each section following the guidance comments. "
                f"Output the complete article including frontmatter."
            )

        # Call LLM to compile
        article_content = self.call_llm(
            messages=[{"role": "user", "content": compile_msg}],
        )

        # Write article
        self.write_file(output_path, article_content)

        # Generate content summary using dedicated summary prompt
        summary_msg = (
            f"Summarize this wiki article:\n\n```markdown\n{article_content}\n```"
        )
        summary_response = self.llm_client.complete(
            messages=[{"role": "user", "content": summary_msg}],
            system=_SUMMARY_SYSTEM_PROMPT,
        )
        content_summary = summary_response.content

        # Persist content summary alongside the article
        summary_path = output_path.with_suffix(".summary.json")
        summary_data = {
            "summary": content_summary,
            "article_path": str(output_path),
            "manifest_key": manifest_key,
            "generated_at": datetime.now(UTC).isoformat(),
        }
        self.write_file(summary_path, json.dumps(summary_data, indent=2))

        # Update manifest with downstream tracking
        now = datetime.now(UTC).isoformat()
        content_hash = hash_content(source_path)
        manifest.set(
            manifest_key,
            ManifestEntry(
                hash=content_hash,
                last_processed=now,
                processed_by="compiler",
            ),
        )
        # Track source→wiki dependency in the source's manifest entry
        source_key = str(source_path.relative_to(self._workspace_root))
        source_entry = manifest.get(source_key)
        if source_entry and manifest_key not in source_entry.downstream:
            source_entry.downstream.append(manifest_key)
        manifest.save()

        return CompilationResult(
            success=True,
            skipped=False,
            output_path=output_path,
            manifest_key=manifest_key,
            content_summary=content_summary,
            message=f"Compiled {source_path.name} → {manifest_key}",
        )

    def run_mission(self, mission: dict[str, str]) -> CompilationResult:
        """Execute a Compiler mission.

        Expects mission dict with 'source_path', 'article_type', and 'title'.
        """
        source_path = Path(mission["source_path"])
        article_type = ArticleType(mission.get("article_type", "concept"))
        title = mission.get("title", source_path.stem)
        return self.compile(source_path, article_type=article_type, title=title)
