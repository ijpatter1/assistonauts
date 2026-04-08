"""Curator agent — cross-referencing and knowledge graph maintenance.

The Curator is a singleton agent responsible for adding backlinks,
"See also" sections, and detecting structural needs (orphan articles,
missing cross-references). It uses multi-pass retrieval to find related
articles and LLM inference to determine which connections to add.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from assistonauts.agents.base import Agent, LLMClientProtocol
from assistonauts.archivist.embeddings import EmbeddingClient
from assistonauts.archivist.retrieval import hybrid_search
from assistonauts.archivist.service import Archivist
from assistonauts.tools.curator import parse_links, scan_backlink_targets

_CURATOR_SYSTEM_PROMPT = """\
You are Curator, a cross-referencing agent for the Assistonauts knowledge base.
Your job is to analyze wiki articles and identify connections between them.

Given an article and a list of potentially related articles (with summaries),
suggest which articles should be cross-linked. Output a "See Also" section
in markdown format with wiki-links to related articles.

Guidelines:
- Only suggest links to articles that are genuinely related in content.
- Use [[slug]] format for wiki-links.
- Include a brief reason for each suggested link.
- If no connections are warranted, output "No cross-references needed."
- Do NOT invent article slugs — only use the slugs provided to you.
"""


@dataclass
class CuratorResult:
    """Result of a Curator cross-referencing operation."""

    success: bool
    output_path: Path | None = None
    output_paths: list[Path] = field(default_factory=list)
    links_added: list[str] = field(default_factory=list)
    message: str = ""


class CuratorAgent(Agent):
    """Curator agent — singleton for cross-referencing.

    Owns: wiki/ (link sections only — does not modify article content)
    Reads: index/, wiki/
    """

    def __init__(
        self,
        llm_client: LLMClientProtocol,
        workspace_root: Path,
        archivist: Archivist | None = None,
        embedding_client: EmbeddingClient | None = None,
    ) -> None:
        wiki_dir = workspace_root / "wiki"
        index_dir = workspace_root / "index"

        super().__init__(
            role="curator",
            system_prompt=_CURATOR_SYSTEM_PROMPT,
            llm_client=llm_client,
            owned_dirs=[wiki_dir],
            readable_dirs=[index_dir, wiki_dir],
            toolkit={
                "parse_links": parse_links,
                "scan_backlink_targets": scan_backlink_targets,
            },
        )
        self._workspace_root = workspace_root
        self._archivist = archivist
        self._embedding_client = embedding_client

    def cross_reference(
        self,
        article_path: str,
        archivist: Archivist | None = None,
        embedding_client: EmbeddingClient | None = None,
    ) -> CuratorResult:
        """Cross-reference a single article against the knowledge base.

        Pipeline:
        1. Read the target article
        2. Find related articles via hybrid search
        3. Ask LLM which connections to add
        4. Append "See Also" section if not already present
        """
        arch = archivist or self._archivist
        emb = embedding_client or self._embedding_client
        if arch is None or emb is None:
            return CuratorResult(
                success=False,
                message="Archivist and embedding client required.",
            )

        full_path = self._workspace_root / article_path
        if not full_path.exists():
            return CuratorResult(
                success=False,
                message=f"Article not found: {article_path}",
            )

        content = full_path.read_text()
        existing_links = parse_links(content)

        # Find related articles via hybrid search
        query_embedding = emb.embed(content[:1000])
        # Extract a short query from the title/first paragraph
        title_line = ""
        for line in content.splitlines():
            if line.startswith("# "):
                title_line = line[2:].strip()
                break

        related = hybrid_search(
            arch.db,
            query=title_line or article_path,
            query_embedding=query_embedding,
            limit=10,
        )

        # Filter out self and already-linked articles
        candidates: list[dict[str, object]] = []
        for result in related:
            if result.path == article_path:
                continue
            slug = Path(str(result.path)).stem
            if slug in existing_links:
                continue
            article_meta = arch.db.get_article(result.path)
            if article_meta:
                summary = arch.db.get_summary(result.path)
                article_meta["summary"] = summary["content_summary"] if summary else ""
                candidates.append(article_meta)

        if not candidates:
            return CuratorResult(
                success=True,
                output_path=full_path,
                output_paths=[full_path],
                message="No new cross-references found.",
            )

        # Build prompt for LLM
        candidate_descriptions = []
        for c in candidates[:10]:
            slug = Path(str(c["path"])).stem
            desc = f"- [[{slug}]]: {c.get('title', slug)}"
            if c.get("summary"):
                desc += f" — {c['summary']}"
            candidate_descriptions.append(desc)

        prompt = (
            f"Article: {title_line or article_path}\n\n"
            f"Current content excerpt:\n"
            f"{content[:500]}\n\n"
            f"Potentially related articles:\n"
            + "\n".join(candidate_descriptions)
            + "\n\nSuggest a 'See Also' section with wiki-links "
            "to genuinely related articles from the list above."
        )

        llm_response = self.call_llm(
            messages=[{"role": "user", "content": prompt}],
        )

        # Parse suggested links from LLM response
        suggested_links = parse_links(llm_response)
        new_links = [link for link in suggested_links if link not in existing_links]

        if new_links and "## See Also" not in content:
            # Append See Also section
            see_also = "\n\n## See Also\n\n"
            for link in new_links:
                see_also += f"- [[{link}]]\n"
            updated_content = content.rstrip() + see_also
            self.write_file(full_path, updated_content)

        return CuratorResult(
            success=True,
            output_path=full_path,
            output_paths=[full_path],
            links_added=new_links,
            message=f"Added {len(new_links)} cross-references.",
        )

    def run_mission(self, mission: dict[str, str]) -> CuratorResult:
        """Execute a Curator mission.

        Expects mission dict with 'article_path'.
        """
        article_path = mission["article_path"]
        return self.cross_reference(article_path)
