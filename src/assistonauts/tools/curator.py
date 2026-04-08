"""Curator toolkit — backlink scanner and graph analyzer.

All functions are deterministic (no LLM inference). They parse wiki-links,
build a connectivity graph, and compute metrics for the Curator agent.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path


def parse_links(text: str) -> list[str]:
    """Extract wiki-links ([[slug]] or [[slug|display]]) from markdown.

    Returns a deduplicated list of link slugs.
    """
    # Match [[slug]] or [[slug|display text]]
    matches = re.findall(r"\[\[([^\]|]+)(?:\|[^\]]+)?\]\]", text)
    seen: set[str] = set()
    result: list[str] = []
    for match in matches:
        slug = match.strip()
        if slug not in seen:
            seen.add(slug)
            result.append(slug)
    return result


@dataclass
class BacklinkTarget:
    """A detected backlink target — article A links to slug B."""

    source_path: Path
    target_slug: str


def scan_backlink_targets(wiki_dir: Path) -> list[BacklinkTarget]:
    """Scan all wiki articles and identify backlink targets.

    For each article, parse its wiki-links. Each link creates a
    BacklinkTarget entry showing which article links to which slug.
    """
    targets: list[BacklinkTarget] = []
    if not wiki_dir.exists():
        return targets

    for md_file in wiki_dir.rglob("*.md"):
        content = md_file.read_text()
        links = parse_links(content)
        for slug in links:
            targets.append(BacklinkTarget(source_path=md_file, target_slug=slug))

    return targets


@dataclass
class GraphMetrics:
    """Connectivity metrics for the wiki knowledge graph."""

    total_articles: int = 0
    total_links: int = 0
    orphans: list[str] = field(default_factory=list)
    density: float = 0.0


def analyze_graph(
    links: dict[str, list[str]],
    all_articles: list[str],
) -> GraphMetrics:
    """Analyze the wiki connectivity graph.

    Args:
        links: Dict mapping article path → list of outgoing link slugs.
        all_articles: List of all article paths in the wiki.

    Returns:
        GraphMetrics with orphan detection and density calculation.
    """
    if not all_articles:
        return GraphMetrics()

    total_links = sum(len(v) for v in links.values())

    # Build sets of articles with connections
    has_outgoing: set[str] = set()
    has_incoming: set[str] = set()

    for source, targets in links.items():
        if targets:
            has_outgoing.add(source)
        for target in targets:
            # Match target slug to article paths
            for article in all_articles:
                if target in article:
                    has_incoming.add(article)

    connected = has_outgoing | has_incoming
    orphans = [a for a in all_articles if a not in connected]

    # Density: actual links / possible links (directed graph)
    n = len(all_articles)
    max_links = n * (n - 1) if n > 1 else 1
    density = total_links / max_links if max_links > 0 else 0.0

    return GraphMetrics(
        total_articles=n,
        total_links=total_links,
        orphans=orphans,
        density=density,
    )
