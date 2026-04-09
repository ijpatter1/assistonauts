"""Compiler agent — transforms raw sources into structured wiki articles."""

from __future__ import annotations

import hashlib
import json
import logging
import re
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

import yaml

from assistonauts.agents.base import Agent, LLMClientProtocol
from assistonauts.cache.content import Manifest, ManifestEntry, hash_content
from assistonauts.models.schema import ArticleType, get_default_schema
from assistonauts.templates.engine import render_template
from assistonauts.tools.compiler import generate_diff

logger = logging.getLogger(__name__)

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
- For the frontmatter `sources:` field, use the source filenames provided in
  the template's sources list, not from the raw content's own frontmatter.
  The raw source material may reference original filenames (e.g. .png files)
  that differ from the processed .md filenames in the template.
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

_PLAN_SYSTEM_PROMPT = """\
You are the editorial triage agent for the Assistonauts knowledge base.
Given a set of raw source documents, analyze their content and propose
a compilation plan — what wiki articles to create from this material.

For each proposed article, specify:
- title: a clear, descriptive title
- type: one of concept, entity, log, exploration
- sources: which raw source filenames should be compiled into this article
- rationale: brief explanation of why this grouping and type

Article type guidelines:
- concept: ideas, techniques, principles, explanations, how-things-work
- entity: specific things (a person, object, place, event, product)
- log: records, metadata, reference material, chronological entries
- exploration: open-ended analysis, synthesis, or Q&A

Guidelines:
- Group related sources into a single article when they cover the same topic.
- A source may only appear in one article.
- Every source must be assigned to exactly one article.
- Prefer fewer, richer articles over many thin ones.

Output ONLY valid YAML in this exact format:
```yaml
articles:
  - title: "Article Title"
    type: concept
    sources:
      - filename1.md
      - filename2.md
    rationale: "Why this grouping."
```
"""


@dataclass
class PlannedArticle:
    """A single article proposed by the Compiler's plan mode."""

    title: str
    article_type: ArticleType
    source_paths: list[Path]
    rationale: str = ""


@dataclass
class CompilationPlan:
    """A proposed compilation plan from Compiler plan mode."""

    articles: list[PlannedArticle] = field(default_factory=list)

    def save(self, plans_dir: Path, workspace_root: Path | None = None) -> Path:
        """Persist the plan as a YAML artifact.

        Writes to plans_dir/plan-<timestamp>.yaml. Returns the path.
        If workspace_root is provided, source paths are stored as
        workspace-relative; otherwise falls back to filename only.
        """
        plans_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
        plan_path = plans_dir / f"plan-{timestamp}.yaml"

        def _rel_source(p: Path) -> str:
            if workspace_root is not None:
                try:
                    return str(p.relative_to(workspace_root))
                except ValueError:
                    pass
            return p.name

        data = {
            "created_at": datetime.now(UTC).isoformat(),
            "article_count": len(self.articles),
            "articles": [
                {
                    "title": a.title,
                    "type": a.article_type.value,
                    "sources": [_rel_source(p) for p in a.source_paths],
                    "rationale": a.rationale,
                }
                for a in self.articles
            ],
        }
        plan_path.write_text(yaml.dump(data, default_flow_style=False))
        return plan_path


def _parse_plan_yaml(
    response: str,
    source_lookup: dict[str, Path],
) -> CompilationPlan | None:
    """Parse LLM plan response into a CompilationPlan.

    Returns None if parsing fails.
    """
    # Strip markdown code fences if present
    cleaned = re.sub(r"```ya?ml?\n?", "", response)
    cleaned = re.sub(r"```\n?", "", cleaned)

    try:
        data = yaml.safe_load(cleaned)
    except yaml.YAMLError:
        return None

    if not isinstance(data, dict) or not isinstance(data.get("articles"), list):
        return None

    articles: list[PlannedArticle] = []
    for item in data["articles"]:
        if not isinstance(item, dict):
            continue
        title = str(item.get("title", ""))
        type_str = str(item.get("type", "concept"))
        try:
            article_type = ArticleType(type_str)
        except ValueError:
            article_type = ArticleType.CONCEPT

        source_names = item.get("sources", [])
        source_paths: list[Path] = []
        for name in source_names:
            name = str(name)
            if name in source_lookup:
                source_paths.append(source_lookup[name])

        rationale = str(item.get("rationale", ""))

        if title and source_paths:
            articles.append(
                PlannedArticle(
                    title=title,
                    article_type=article_type,
                    source_paths=source_paths,
                    rationale=rationale,
                )
            )

    return CompilationPlan(articles=articles) if articles else None


def _strip_code_fences(text: str) -> str:
    """Strip markdown code fences from LLM output.

    LLMs sometimes wrap their output in ```markdown ... ``` fences.
    This strips them so the article is clean markdown.
    """
    stripped = text.strip()
    if stripped.startswith("```"):
        # Remove opening fence (```markdown, ```md, or just ```)
        stripped = re.sub(r"^```\w*\n?", "", stripped, count=1)
        # Remove closing fence
        stripped = re.sub(r"\n?```\s*$", "", stripped)
    return stripped.strip()


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
    output_paths: list[Path] = field(default_factory=list)
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
                "generate_diff": generate_diff,
            },
        )
        self._workspace_root = workspace_root
        self._manifest_path = index_dir / "manifest.json"
        self._schema = get_default_schema()
        self._expedition_scope = expedition_scope
        self._setup_persistent_logger(workspace_root)

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

        # Check if source has changed — manifest keys the output path but
        # stores the hash of the *source* file for skip-if-unchanged logic
        if not manifest.has_changed(source_path, manifest_key):
            return CompilationResult(
                success=True,
                skipped=True,
                output_path=output_path,
                output_paths=[output_path],
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
                f"Source filenames to use in frontmatter: "
                f"{', '.join(sources)}\n\n"
                f"Source material:\n```markdown\n{source_content}\n```\n\n"
                f"Template to fill:\n```markdown\n{template}\n```\n\n"
                f"Fill in each section following the guidance comments. "
                f"Use the source filenames listed above for the "
                f"frontmatter sources field, not filenames found "
                f"inside the raw content. "
                f"Output the complete article including frontmatter."
            )

        # Call LLM to compile
        article_content = _strip_code_fences(
            self.call_llm(
                messages=[{"role": "user", "content": compile_msg}],
            )
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
        rel_article_path = str(output_path.relative_to(self._workspace_root))
        summary_data = {
            "summary": content_summary,
            "article_path": rel_article_path,
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
            output_paths=[output_path, summary_path],
            manifest_key=manifest_key,
            content_summary=content_summary,
            message=f"Compiled {source_path.name} → {manifest_key}",
        )

    def compile_multi(
        self,
        source_paths: list[Path],
        article_type: str | ArticleType,
        title: str,
    ) -> CompilationResult:
        """Compile multiple source files into a single wiki article.

        Concatenates source content in order, tracks all source hashes
        in the manifest, and lists all sources in the article frontmatter.
        Falls back to single-source compile() for one source.
        """
        if not source_paths:
            return CompilationResult(success=False, message="No source paths provided.")

        if isinstance(article_type, str):
            article_type = ArticleType(article_type)

        resolved = [p.resolve() for p in source_paths]
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

        # Check if ANY source has changed — compute combined hash
        source_hashes = [hash_content(p) for p in resolved]
        combined_hash = hashlib.sha256("|".join(source_hashes).encode()).hexdigest()

        existing = manifest.get(manifest_key)
        if existing and existing.hash == combined_hash:
            return CompilationResult(
                success=True,
                skipped=True,
                output_path=output_path,
                output_paths=[output_path],
                manifest_key=manifest_key,
                message="Sources unchanged, skipped.",
            )

        # Concatenate source content with separators
        source_contents: list[str] = []
        for p in resolved:
            source_contents.append(self.read_file(p))

        combined_content = "\n\n---\n\n".join(source_contents)
        source_names = [p.name for p in resolved]

        # Check for existing article (recompilation)
        existing_content = ""
        if output_path.exists():
            existing_content = self.read_file(output_path)

        # Render template scaffold
        template = render_template(
            schema=self._schema,
            article_type=article_type,
            title=title,
            sources=source_names,
        )

        # Build compilation prompt
        if existing_content:
            article_diff = generate_diff("", existing_content)
            compile_msg = (
                f"Recompile this wiki article based on updated "
                f"source material ({len(resolved)} sources).\n\n"
                f"Current article structure: "
                f"{article_diff.summary}\n\n"
                f"Current article:\n"
                f"```markdown\n{existing_content}\n```\n\n"
                f"Updated source material:\n"
                f"```markdown\n{combined_content}\n```\n\n"
                f"Template structure to follow:\n"
                f"```markdown\n{template}\n```\n\n"
                f"Update the article to reflect all source "
                f"material. Output the complete article."
            )
        else:
            compile_msg = (
                f"Compile these {len(resolved)} source documents "
                f"into a single wiki article.\n\n"
                f"Source filenames to use in frontmatter: "
                f"{', '.join(source_names)}\n\n"
                f"Source material:\n"
                f"```markdown\n{combined_content}\n```\n\n"
                f"Template to fill:\n"
                f"```markdown\n{template}\n```\n\n"
                f"Synthesize all sources into a coherent article. "
                f"Use the source filenames listed above for the "
                f"frontmatter sources field, not filenames found "
                f"inside the raw content. "
                f"Output the complete article including frontmatter."
            )

        # Call LLM to compile
        article_content = _strip_code_fences(
            self.call_llm(
                messages=[{"role": "user", "content": compile_msg}],
            )
        )

        # Write article
        self.write_file(output_path, article_content)

        # Generate content summary
        summary_msg = (
            f"Summarize this wiki article:\n\n```markdown\n{article_content}\n```"
        )
        summary_response = self.llm_client.complete(
            messages=[{"role": "user", "content": summary_msg}],
            system=_SUMMARY_SYSTEM_PROMPT,
        )
        content_summary = summary_response.content

        # Persist content summary
        summary_path = output_path.with_suffix(".summary.json")
        rel_article_path = str(output_path.relative_to(self._workspace_root))
        summary_data = {
            "summary": content_summary,
            "article_path": rel_article_path,
            "manifest_key": manifest_key,
            "sources": source_names,
            "generated_at": datetime.now(UTC).isoformat(),
        }
        self.write_file(summary_path, json.dumps(summary_data, indent=2))

        # Update manifest — store combined hash of all sources
        now = datetime.now(UTC).isoformat()
        manifest.set(
            manifest_key,
            ManifestEntry(
                hash=combined_hash,
                last_processed=now,
                processed_by="compiler",
            ),
        )
        # Track source→wiki dependencies
        for p in resolved:
            source_key = str(p.relative_to(self._workspace_root))
            source_entry = manifest.get(source_key)
            if source_entry and manifest_key not in source_entry.downstream:
                source_entry.downstream.append(manifest_key)
        manifest.save()

        return CompilationResult(
            success=True,
            skipped=False,
            output_path=output_path,
            output_paths=[output_path, summary_path],
            manifest_key=manifest_key,
            content_summary=content_summary,
            message=(f"Compiled {len(resolved)} sources → {manifest_key}"),
        )

    def plan(self, source_paths: list[Path]) -> CompilationPlan:
        """Analyze raw sources and propose a compilation plan.

        Reads each source, sends content + schema info to LLM,
        and asks it to propose article groupings, types, and titles.
        Returns a CompilationPlan that can be executed via compile_multi().

        If the LLM response can't be parsed, falls back to one article
        per source, all typed as concept.
        """
        if not source_paths:
            return CompilationPlan()

        resolved = [p.resolve() for p in source_paths]

        # Build source name → path lookup for resolving LLM references
        source_lookup: dict[str, Path] = {}
        for p in resolved:
            source_lookup[p.name] = p

        # Read source content for the prompt
        source_summaries: list[str] = []
        for p in resolved:
            content = self.read_file(p)
            # Truncate long sources for the planning prompt
            preview = content[:2000]
            if len(content) > 2000:
                preview += f"\n... ({len(content)} chars total)"
            source_summaries.append(f"### {p.name}\n{preview}")

        sources_text = "\n\n".join(source_summaries)

        # Build the planning prompt
        scope_line = self._expedition_scope

        prompt = (
            f"Analyze these {len(resolved)} source documents "
            f"and propose a compilation plan.\n\n"
            f"Available article types: concept, entity, log, "
            f"exploration\n\n"
        )
        if scope_line:
            prompt += f"Expedition scope: {scope_line}\n\n"
        prompt += f"Source documents:\n\n{sources_text}"

        # Call LLM with plan-specific system prompt.
        # Can't use self.call_llm() since that uses the compilation
        # system prompt. Log manually for structured logging.
        response = self.llm_client.complete(
            messages=[{"role": "user", "content": prompt}],
            system=_PLAN_SYSTEM_PROMPT,
        )
        assert self.logger is not None
        usage = getattr(response, "usage", {})
        p_tokens = usage.get("prompt_tokens", 0) if isinstance(usage, dict) else 0
        c_tokens = usage.get("completion_tokens", 0) if isinstance(usage, dict) else 0
        self.logger.log_llm_call(
            model=getattr(response, "model", "unknown"),
            prompt_tokens=p_tokens,
            completion_tokens=c_tokens,
        )

        # Parse the response
        plan = _parse_plan_yaml(response.content, source_lookup)

        if plan is not None:
            return plan

        # Fallback: one article per source, all concept type
        logger.warning(
            "Failed to parse compilation plan from LLM response. "
            "Falling back to one article per source."
        )
        fallback_articles = [
            PlannedArticle(
                title=p.stem.replace("-", " ").replace("_", " ").title(),
                article_type=ArticleType.CONCEPT,
                source_paths=[p],
                rationale="Fallback: LLM plan response could not be parsed.",
            )
            for p in resolved
        ]
        return CompilationPlan(articles=fallback_articles)

    def run_task(self, task: dict[str, str]) -> CompilationResult:
        """Execute a Compiler task.

        Expects task dict with 'source_path' (single) or
        'source_paths' (comma-separated list), 'article_type', and 'title'.
        """
        article_type = ArticleType(task.get("article_type", "concept"))

        # Support multi-source via comma-separated paths
        if "source_paths" in task:
            paths = [Path(p.strip()) for p in task["source_paths"].split(",")]
            title = task.get("title", paths[0].stem)
            return self.compile_multi(paths, article_type=article_type, title=title)

        source_path = Path(task["source_path"])
        title = task.get("title", source_path.stem)
        return self.compile(source_path, article_type=article_type, title=title)
