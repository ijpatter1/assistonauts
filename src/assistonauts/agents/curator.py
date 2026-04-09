"""Curator agent — cross-referencing and knowledge graph maintenance.

The Curator is a singleton agent responsible for adding backlinks,
"See also" sections, and detecting structural needs (orphan articles,
missing cross-references). It uses multi-pass retrieval to find related
articles and LLM inference to determine which connections to add.
"""

from __future__ import annotations

import json
import logging
import threading
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from assistonauts.agents.base import Agent, LLMClientProtocol
from assistonauts.archivist.embeddings import EmbeddingClient
from assistonauts.archivist.service import Archivist
from assistonauts.rag.multi_pass import MultiPassRetriever, RetrievalLog
from assistonauts.tools.curator import analyze_graph, parse_links, scan_backlink_targets

_CURATOR_SYSTEM_PROMPT = """\
You are Curator, a cross-referencing agent for the Assistonauts knowledge base.
Your job is to analyze wiki articles and identify connections between them.

Given an article and a list of potentially related articles (with summaries),
classify each connection as STRONG or WEAK and suggest cross-links.

Output format — one line per suggested link:
STRONG [[slug]]: reason for strong connection
WEAK [[slug]]: reason for weak connection

Guidelines:
- STRONG means bidirectional linking is warranted (both articles should
  reference each other). Use for articles that cover closely related topics,
  share core concepts, or where understanding one requires the other.
- WEAK means "See also" only on the target article. Use for tangentially
  related articles where a one-way pointer is sufficient.
- Only suggest links to articles that are genuinely related in content.
- Use [[slug]] format for wiki-links.
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
    backlinks_added: list[str] = field(default_factory=list)
    message: str = ""


class CuratorAgent(Agent):
    """Curator agent — singleton for cross-referencing.

    Owns: wiki/ (link sections only — does not modify article content)
    Reads: index/, wiki/

    Singleton enforcement: only one CuratorAgent instance may be active
    at a time. Creating a second instance while one is alive raises
    RuntimeError.
    """

    _lock: threading.Lock = threading.Lock()
    _active_instance: CuratorAgent | None = None

    def __init__(
        self,
        llm_client: LLMClientProtocol,
        workspace_root: Path,
        archivist: Archivist | None = None,
        embedding_client: EmbeddingClient | None = None,
    ) -> None:
        with CuratorAgent._lock:
            if CuratorAgent._active_instance is not None:
                raise RuntimeError(
                    "A CuratorAgent instance is already active. "
                    "Call close() on the existing instance before creating a new one."
                )
            CuratorAgent._active_instance = self

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
        self._setup_persistent_logger(workspace_root)

    def close(self) -> None:
        """Release the singleton lock so a new instance can be created."""
        with CuratorAgent._lock:
            if CuratorAgent._active_instance is self:
                CuratorAgent._active_instance = None

    def cross_reference(
        self,
        article_path: str,
        archivist: Archivist | None = None,
        embedding_client: EmbeddingClient | None = None,
    ) -> CuratorResult:
        """Cross-reference a single article against the knowledge base.

        Pipeline:
        1. Read the target article
        2. Find related articles via multi-pass retrieval
        3. Ask LLM to classify connections as STRONG or WEAK
        4. STRONG: bidirectional backlinks (update both articles)
        5. WEAK: "See Also" on target article only
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

        # Extract title from frontmatter or heading
        title_line = _extract_title(content)

        # Find related articles via multi-pass retrieval
        retriever = MultiPassRetriever(
            archivist=arch,
            embedding_client=emb,
            llm_client=self.llm_client,
        )
        retrieval_result = retriever.retrieve(title_line or article_path)

        # Filter out self and already-linked articles
        candidates: list[dict[str, object]] = []
        for article in retrieval_result.articles:
            if str(article.get("path", "")) == article_path:
                continue
            slug = Path(str(article["path"])).stem
            if slug in existing_links:
                continue
            # Enrich with summary if available
            summary = arch.db.get_summary(str(article["path"]))
            if summary:
                article["summary"] = summary["content_summary"]
            candidates.append(article)

        if not candidates:
            return CuratorResult(
                success=True,
                output_path=full_path,
                output_paths=[full_path],
                message="No new cross-references found.",
            )

        # Build prompt asking LLM to classify STRONG vs WEAK
        candidate_descriptions = []
        for c in candidates:
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
            + "\n\nClassify each connection as STRONG or WEAK. "
            "Use format: STRONG [[slug]]: reason  or  WEAK [[slug]]: reason"
        )

        llm_response = self.call_llm(
            messages=[{"role": "user", "content": prompt}],
        )

        # Parse classified links from LLM response
        strong_links, weak_links = _parse_classified_links(llm_response, existing_links)
        all_new_links = strong_links + weak_links

        # Write "See Also" / append to target article for all new links
        modified_paths: list[Path] = []
        if all_new_links:
            self._write_see_also(full_path, all_new_links)
            modified_paths.append(full_path)

        # Bidirectional: add backlinks FROM related articles TO target
        target_slug = Path(article_path).stem
        backlinks_added: list[str] = []
        for slug in strong_links:
            backlink_path = self._find_article_path(slug, arch)
            if backlink_path is None:
                continue
            related_content = backlink_path.read_text()
            related_existing = parse_links(related_content)
            if target_slug in related_existing:
                continue
            self._write_see_also(backlink_path, [target_slug])
            backlinks_added.append(slug)
            modified_paths.append(backlink_path)

        result = CuratorResult(
            success=True,
            output_path=full_path,
            output_paths=modified_paths,
            links_added=all_new_links,
            backlinks_added=backlinks_added,
            message=(
                f"Added {len(all_new_links)} cross-references "
                f"({len(strong_links)} strong, {len(weak_links)} weak), "
                f"{len(backlinks_added)} backlinks."
            ),
        )

        self._log_cross_reference(
            article_path=article_path,
            candidates=[Path(str(c["path"])).stem for c in candidates],
            strong_links=strong_links,
            weak_links=weak_links,
            backlinks_added=backlinks_added,
            retrieval_log=retrieval_result.log,
        )

        return result

    def _log_cross_reference(
        self,
        article_path: str,
        candidates: list[str],
        strong_links: list[str],
        weak_links: list[str],
        backlinks_added: list[str],
        retrieval_log: RetrievalLog | None = None,
    ) -> None:
        """Append a cross-reference decision record to .assistonauts/curator/.

        Every cross_reference() call is logged for audit trail.
        Best-effort — logging failures never crash the primary operation.
        """
        try:
            log_dir = self._workspace_root / ".assistonauts" / "curator"
            log_dir.mkdir(parents=True, exist_ok=True)
            log_path = log_dir / "cross-references.jsonl"

            entry: dict[str, object] = {
                "timestamp": datetime.now(UTC).isoformat(),
                "article": article_path,
                "candidates_evaluated": candidates,
                "strong_links": strong_links,
                "weak_links": weak_links,
                "backlinks_added": backlinks_added,
            }

            if retrieval_log is not None:
                entry["retrieval"] = retrieval_log.to_dict()

            with open(log_path, "a") as f:
                f.write(json.dumps(entry, default=str) + "\n")
        except Exception:
            logging.getLogger(__name__).warning(
                "Failed to write curator audit log", exc_info=True
            )

    def _write_see_also(self, path: Path, slugs: list[str]) -> None:
        """Append wiki-links to an article's See Also section via write_file."""
        content = path.read_text()
        new_entries = "".join(f"- [[{slug}]]\n" for slug in slugs)
        if "## See Also" in content:
            updated = content.rstrip() + "\n" + new_entries
        else:
            updated = content.rstrip() + "\n\n## See Also\n\n" + new_entries
        self.write_file(path, updated)

    def _find_article_path(self, slug: str, archivist: Archivist) -> Path | None:
        """Find the full path for an article by its slug."""
        all_articles = archivist.db.list_articles()
        for article in all_articles:
            if Path(str(article["path"])).stem == slug:
                return self._workspace_root / str(article["path"])
        return None

    def retroactive_cross_reference(self) -> list[CuratorResult]:
        """Run cross-referencing over all indexed articles.

        Used after the Archivist index is first built to add backlinks
        and "See also" sections to articles from Phases 1-2 that were
        compiled before the index existed.
        """
        arch = self._archivist
        emb = self._embedding_client
        if arch is None or emb is None:
            return []

        all_articles = arch.db.list_articles()
        results: list[CuratorResult] = []
        for article in all_articles:
            path = str(article["path"])
            result = self.cross_reference(path)
            results.append(result)
        return results

    def generate_proposals(self) -> list[dict[str, str]]:
        """Detect structural issues and generate improvement proposals.

        Uses the graph analyzer from the toolkit to detect orphans,
        low connectivity, and structural gaps. Returns a list of
        proposal dicts with 'type', 'target', and 'reason' keys.
        """
        arch = self._archivist
        if arch is None:
            return []

        wiki_dir = self._workspace_root / "wiki"
        all_articles = [str(a["path"]) for a in arch.db.list_articles()]
        if not all_articles:
            return []

        # Build link graph from wiki directory
        backlink_targets = scan_backlink_targets(wiki_dir)
        links: dict[str, list[str]] = {a: [] for a in all_articles}
        for bt in backlink_targets:
            # Map source_path back to relative path
            try:
                rel = str(bt.source_path.relative_to(self._workspace_root))
            except ValueError:
                continue
            if rel in links:
                links[rel].append(bt.target_slug)

        metrics = analyze_graph(links, all_articles)

        proposals: list[dict[str, str]] = []

        # Orphan proposals
        for orphan in metrics.orphans:
            proposals.append(
                {
                    "type": "orphan",
                    "target": orphan,
                    "reason": "Article has no incoming or outgoing links.",
                }
            )

        # Low connectivity proposal
        if metrics.density < 0.1 and metrics.total_articles > 3:
            proposals.append(
                {
                    "type": "low_connectivity",
                    "target": "knowledge_base",
                    "reason": (
                        f"Graph density is {metrics.density:.3f} — "
                        "consider adding more cross-references."
                    ),
                }
            )

        return proposals

    def run_task(self, task: dict[str, str]) -> CuratorResult:
        """Execute a Curator task.

        Expects task dict with 'article_path'.
        """
        article_path = task["article_path"]
        return self.cross_reference(article_path)


def _extract_title(content: str) -> str:
    """Extract article title from YAML frontmatter or heading."""
    # Try frontmatter title: field first
    in_frontmatter = False
    for line in content.splitlines():
        if line.strip() == "---":
            if not in_frontmatter:
                in_frontmatter = True
                continue
            break  # End of frontmatter
        if in_frontmatter and line.startswith("title:"):
            return line.split(":", 1)[1].strip().strip("\"'")

    # Fall back to first heading
    for line in content.splitlines():
        if line.startswith("# "):
            return line[2:].strip()
    return ""


def _parse_classified_links(
    llm_response: str,
    existing_links: list[str],
) -> tuple[list[str], list[str]]:
    """Parse LLM response for STRONG/WEAK classified links.

    Returns (strong_links, weak_links) — deduplicated, excluding existing.

    Handles three formats:
    - "STRONG [[slug]]: reason" / "WEAK [[slug]]: reason"
    - "## See Also\\n- [[slug]]" (legacy format, treated as weak)
    - Plain "[[slug]]" (treated as weak)
    """
    strong: list[str] = []
    weak: list[str] = []
    seen: set[str] = set(existing_links)

    for line in llm_response.splitlines():
        stripped = line.strip()
        links_in_line = parse_links(stripped)
        if not links_in_line:
            continue

        slug = links_in_line[0]
        if slug in seen:
            continue
        seen.add(slug)

        upper = stripped.upper()
        if upper.startswith("STRONG"):
            strong.append(slug)
        else:
            # WEAK, or any unclassified format (legacy "## See Also")
            weak.append(slug)

    return strong, weak
