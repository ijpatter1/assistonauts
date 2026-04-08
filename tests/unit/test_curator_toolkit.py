"""Tests for the Curator toolkit — backlink scanner and graph analyzer."""

from __future__ import annotations

from pathlib import Path

from assistonauts.tools.curator import (
    analyze_graph,
    parse_links,
    scan_backlink_targets,
)

_ARTICLE_WITH_LINKS = """\
---
title: Spectral Analysis
type: concept
---

# Spectral Analysis

This builds on [[frequency-domain]] concepts.
See also [[time-series]] for related analysis methods.

## See Also

- [[neural-networks]]
"""

_ARTICLE_NO_LINKS = """\
---
title: Orphan Article
type: concept
---

# Orphan Article

This article has no links to other articles.
"""


class TestParseLinks:
    """Test wiki-link extraction from markdown."""

    def test_extracts_wiki_links(self) -> None:
        links = parse_links(_ARTICLE_WITH_LINKS)
        assert "frequency-domain" in links
        assert "time-series" in links
        assert "neural-networks" in links

    def test_no_links(self) -> None:
        links = parse_links(_ARTICLE_NO_LINKS)
        assert links == []

    def test_deduplicates(self) -> None:
        text = "See [[foo]] and also [[foo]] again."
        links = parse_links(text)
        assert links == ["foo"]

    def test_handles_display_text(self) -> None:
        text = "See [[spectral-analysis|Spectral Analysis]] for details."
        links = parse_links(text)
        assert "spectral-analysis" in links


class TestScanBacklinkTargets:
    """Test the backlink target scanner."""

    def test_identifies_targets(self, tmp_path: Path) -> None:
        # Create articles
        concepts = tmp_path / "wiki" / "concepts"
        concepts.mkdir(parents=True)
        (concepts / "spectral.md").write_text(_ARTICLE_WITH_LINKS)
        (concepts / "frequency-domain.md").write_text(_ARTICLE_NO_LINKS)

        targets = scan_backlink_targets(tmp_path / "wiki")
        # spectral links to frequency-domain, so frequency-domain
        # should show as a backlink target
        freq_targets = [t for t in targets if t.target_slug == "frequency-domain"]
        assert len(freq_targets) >= 1
        assert freq_targets[0].source_path.name == "spectral.md"

    def test_empty_wiki(self, tmp_path: Path) -> None:
        wiki = tmp_path / "wiki"
        wiki.mkdir()
        targets = scan_backlink_targets(wiki)
        assert targets == []


class TestGraphAnalyzer:
    """Test the connectivity graph analyzer."""

    def test_detects_orphans(self) -> None:
        # Build a graph: a→b, c is orphaned (no incoming or outgoing)
        links = {
            "a.md": ["b"],
            "b.md": [],
            "c.md": [],
        }
        all_articles = ["a.md", "b.md", "c.md"]
        metrics = analyze_graph(links, all_articles)
        assert "c.md" in metrics.orphans
        # a has outgoing links, b has incoming — neither are orphans
        assert "a.md" not in metrics.orphans
        assert "b.md" not in metrics.orphans

    def test_connectivity_metrics(self) -> None:
        links = {
            "a.md": ["b", "c"],
            "b.md": ["a"],
            "c.md": [],
        }
        all_articles = ["a.md", "b.md", "c.md"]
        metrics = analyze_graph(links, all_articles)
        assert metrics.total_articles == 3
        assert metrics.total_links >= 3
        assert 0.0 <= metrics.density <= 1.0

    def test_empty_graph(self) -> None:
        metrics = analyze_graph({}, [])
        assert metrics.total_articles == 0
        assert metrics.orphans == []
        assert metrics.density == 0.0

    def test_fully_connected(self) -> None:
        links = {
            "a.md": ["b"],
            "b.md": ["a"],
        }
        metrics = analyze_graph(links, ["a.md", "b.md"])
        assert metrics.orphans == []
        assert metrics.density > 0.0
