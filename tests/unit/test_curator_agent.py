"""Tests for the Curator agent — cross-referencing pipeline."""

from __future__ import annotations

from pathlib import Path

import pytest

from assistonauts.agents.curator import CuratorAgent
from assistonauts.archivist.service import Archivist
from tests.helpers import FakeEmbeddingClient, FakeLLMClient

_ARTICLE_SPECTRAL = """\
---
title: Spectral Analysis
type: concept
sources:
  - raw/papers/fft.md
tags:
  - signal-processing
---

# Spectral Analysis

Spectral analysis decomposes signals into frequency components
using Fourier transforms.

## Key Concepts

The fast Fourier transform (FFT) is the most common algorithm.

## Sources

- raw/papers/fft.md
"""

_ARTICLE_FREQUENCY = """\
---
title: Frequency Domain
type: concept
sources:
  - raw/papers/signals.md
tags:
  - signal-processing
---

# Frequency Domain

The frequency domain represents signals as sums of sinusoids.
Closely related to spectral analysis methods.

## Sources

- raw/papers/signals.md
"""


@pytest.fixture(autouse=True)
def _reset_curator_singleton() -> None:  # type: ignore[misc]
    """Reset the CuratorAgent singleton between tests."""
    CuratorAgent._active_instance = None
    yield  # type: ignore[misc]
    CuratorAgent._active_instance = None


@pytest.fixture
def workspace(initialized_workspace: Path) -> Path:
    return initialized_workspace


@pytest.fixture
def archivist(workspace: Path) -> Archivist:
    return Archivist(workspace, embedding_dimensions=4)


@pytest.fixture
def embedding_client() -> FakeEmbeddingClient:
    return FakeEmbeddingClient(dimensions=4)


def _populate_kb(
    workspace: Path,
    archivist: Archivist,
    embedding_client: FakeEmbeddingClient,
) -> None:
    """Write and index test articles."""
    articles = {
        "wiki/concepts/spectral-analysis.md": _ARTICLE_SPECTRAL,
        "wiki/concepts/frequency-domain.md": _ARTICLE_FREQUENCY,
    }
    for rel_path, content in articles.items():
        full = workspace / rel_path
        full.parent.mkdir(parents=True, exist_ok=True)
        full.write_text(content)
        archivist.index_with_embeddings(rel_path, embedding_client=embedding_client)


class TestCuratorAgent:
    """Test Curator agent initialization and basic behavior."""

    def test_curator_role(self, workspace: Path) -> None:
        llm = FakeLLMClient(responses=["## See Also\n\n- [[frequency-domain]]"])
        curator = CuratorAgent(
            llm_client=llm,
            workspace_root=workspace,
        )
        assert curator.role == "curator"

    def test_curator_owns_wiki(self, workspace: Path) -> None:
        llm = FakeLLMClient()
        curator = CuratorAgent(
            llm_client=llm,
            workspace_root=workspace,
        )
        wiki_dir = workspace / "wiki"
        assert any(d.resolve() == wiki_dir.resolve() for d in curator.owned_dirs)

    def test_curator_reads_index(self, workspace: Path) -> None:
        llm = FakeLLMClient()
        curator = CuratorAgent(
            llm_client=llm,
            workspace_root=workspace,
        )
        index_dir = workspace / "index"
        readable = [d.resolve() for d in curator.readable_dirs]
        assert index_dir.resolve() in readable


class TestCuratorCrossReference:
    """Test the cross-referencing pipeline."""

    def test_cross_reference_adds_links(
        self,
        workspace: Path,
        archivist: Archivist,
        embedding_client: FakeEmbeddingClient,
    ) -> None:
        _populate_kb(workspace, archivist, embedding_client)
        llm = FakeLLMClient(responses=["## See Also\n\n- [[frequency-domain]]"])
        curator = CuratorAgent(
            llm_client=llm,
            workspace_root=workspace,
        )
        result = curator.cross_reference(
            "wiki/concepts/spectral-analysis.md",
            archivist=archivist,
            embedding_client=embedding_client,
        )
        assert result.success is True

    def test_cross_reference_result_has_links(
        self,
        workspace: Path,
        archivist: Archivist,
        embedding_client: FakeEmbeddingClient,
    ) -> None:
        _populate_kb(workspace, archivist, embedding_client)
        llm = FakeLLMClient(responses=["## See Also\n\n- [[frequency-domain]]"])
        curator = CuratorAgent(
            llm_client=llm,
            workspace_root=workspace,
        )
        result = curator.cross_reference(
            "wiki/concepts/spectral-analysis.md",
            archivist=archivist,
            embedding_client=embedding_client,
        )
        assert "frequency-domain" in result.links_added

    def test_cross_reference_writes_see_also_to_file(
        self,
        workspace: Path,
        archivist: Archivist,
        embedding_client: FakeEmbeddingClient,
    ) -> None:
        """cross_reference() must actually write See Also to the article file."""
        _populate_kb(workspace, archivist, embedding_client)
        llm = FakeLLMClient(responses=["## See Also\n\n- [[frequency-domain]]"])
        curator = CuratorAgent(
            llm_client=llm,
            workspace_root=workspace,
        )
        curator.cross_reference(
            "wiki/concepts/spectral-analysis.md",
            archivist=archivist,
            embedding_client=embedding_client,
        )
        content = (workspace / "wiki/concepts/spectral-analysis.md").read_text()
        assert "## See Also" in content
        assert "[[frequency-domain]]" in content

    def test_cross_reference_appends_to_existing_see_also(
        self,
        workspace: Path,
        archivist: Archivist,
        embedding_client: FakeEmbeddingClient,
    ) -> None:
        """New links must be appended even if See Also already exists."""
        _populate_kb(workspace, archivist, embedding_client)

        # Pre-populate See Also with a different link
        article_path = workspace / "wiki/concepts/spectral-analysis.md"
        original = article_path.read_text()
        article_path.write_text(
            original.rstrip() + "\n\n## See Also\n\n- [[existing-link]]\n"
        )

        llm = FakeLLMClient(responses=["## See Also\n\n- [[frequency-domain]]"])
        curator = CuratorAgent(
            llm_client=llm,
            workspace_root=workspace,
        )
        result = curator.cross_reference(
            "wiki/concepts/spectral-analysis.md",
            archivist=archivist,
            embedding_client=embedding_client,
        )
        content = article_path.read_text()
        assert "[[existing-link]]" in content, "Existing links must be preserved"
        assert "[[frequency-domain]]" in content, "New links must be appended"
        assert "frequency-domain" in result.links_added

    def test_run_task(
        self,
        workspace: Path,
        archivist: Archivist,
        embedding_client: FakeEmbeddingClient,
    ) -> None:
        _populate_kb(workspace, archivist, embedding_client)
        llm = FakeLLMClient(responses=["## See Also\n\n- [[frequency-domain]]"])
        curator = CuratorAgent(
            llm_client=llm,
            workspace_root=workspace,
            archivist=archivist,
            embedding_client=embedding_client,
        )
        result = curator.run_task(
            {"article_path": "wiki/concepts/spectral-analysis.md"}
        )
        assert result.success is True


class TestCuratorSingleton:
    """Test singleton enforcement for CuratorAgent."""

    def test_second_instance_raises(self, workspace: Path) -> None:
        """Creating a second CuratorAgent while one is active raises."""
        llm = FakeLLMClient()
        curator1 = CuratorAgent(llm_client=llm, workspace_root=workspace)
        with pytest.raises(RuntimeError, match="already active"):
            CuratorAgent(llm_client=llm, workspace_root=workspace)
        curator1.close()

    def test_close_allows_new_instance(self, workspace: Path) -> None:
        """After close(), a new instance can be created."""
        llm = FakeLLMClient()
        curator1 = CuratorAgent(llm_client=llm, workspace_root=workspace)
        curator1.close()
        curator2 = CuratorAgent(llm_client=llm, workspace_root=workspace)
        assert curator2.role == "curator"
        curator2.close()


class TestCuratorMultiPass:
    """Test that cross-referencing uses multi-pass retrieval."""

    def test_cross_reference_uses_multi_pass(
        self,
        workspace: Path,
        archivist: Archivist,
        embedding_client: FakeEmbeddingClient,
    ) -> None:
        """cross_reference() should route through MultiPassRetriever."""
        _populate_kb(workspace, archivist, embedding_client)
        llm = FakeLLMClient(responses=["## See Also\n\n- [[frequency-domain]]"])
        curator = CuratorAgent(
            llm_client=llm,
            workspace_root=workspace,
            archivist=archivist,
            embedding_client=embedding_client,
        )
        result = curator.cross_reference(
            "wiki/concepts/spectral-analysis.md",
            archivist=archivist,
            embedding_client=embedding_client,
        )
        assert result.success is True
        # Multi-pass should still find related articles and produce links
        content = (workspace / "wiki/concepts/spectral-analysis.md").read_text()
        assert "## See Also" in content


class TestCuratorBidirectional:
    """Test bidirectional linking for strong matches."""

    def test_strong_match_updates_both_articles(
        self,
        workspace: Path,
        archivist: Archivist,
        embedding_client: FakeEmbeddingClient,
    ) -> None:
        """Strong matches should add backlinks to the related article too."""
        _populate_kb(workspace, archivist, embedding_client)
        # LLM response for cross-referencing: first for link suggestions,
        # then for classifying strong/weak (STRONG response)
        llm = FakeLLMClient(
            responses=[
                "STRONG [[frequency-domain]]: closely related topic",
            ]
        )
        curator = CuratorAgent(
            llm_client=llm,
            workspace_root=workspace,
            archivist=archivist,
            embedding_client=embedding_client,
        )
        result = curator.cross_reference(
            "wiki/concepts/spectral-analysis.md",
            archivist=archivist,
            embedding_client=embedding_client,
        )
        assert result.success is True

        # Target article should have See Also
        target = (workspace / "wiki/concepts/spectral-analysis.md").read_text()
        assert "[[frequency-domain]]" in target

        # Related article should have backlink to target (bidirectional)
        related = (workspace / "wiki/concepts/frequency-domain.md").read_text()
        assert "[[spectral-analysis]]" in related

    def test_weak_match_only_updates_target(
        self,
        workspace: Path,
        archivist: Archivist,
        embedding_client: FakeEmbeddingClient,
    ) -> None:
        """Weak matches should only add See Also to the target, not backlinks."""
        _populate_kb(workspace, archivist, embedding_client)
        llm = FakeLLMClient(
            responses=[
                "WEAK [[frequency-domain]]: tangentially related",
            ]
        )
        curator = CuratorAgent(
            llm_client=llm,
            workspace_root=workspace,
            archivist=archivist,
            embedding_client=embedding_client,
        )
        result = curator.cross_reference(
            "wiki/concepts/spectral-analysis.md",
            archivist=archivist,
            embedding_client=embedding_client,
        )
        assert result.success is True

        # Target should have See Also
        target = (workspace / "wiki/concepts/spectral-analysis.md").read_text()
        assert "[[frequency-domain]]" in target

        # Related article should NOT have backlink (weak match)
        related = (workspace / "wiki/concepts/frequency-domain.md").read_text()
        assert "[[spectral-analysis]]" not in related


class TestCuratorGenerateProposals:
    """Test the generate_proposals method."""

    def test_generates_orphan_proposals(
        self,
        workspace: Path,
        archivist: Archivist,
        embedding_client: FakeEmbeddingClient,
    ) -> None:
        """Orphan articles should generate proposals."""
        _populate_kb(workspace, archivist, embedding_client)
        llm = FakeLLMClient()
        curator = CuratorAgent(
            llm_client=llm,
            workspace_root=workspace,
            archivist=archivist,
            embedding_client=embedding_client,
        )
        proposals = curator.generate_proposals()
        # Both articles have no links, so both should be orphans
        orphan_proposals = [p for p in proposals if p["type"] == "orphan"]
        assert len(orphan_proposals) >= 1

    def test_no_proposals_without_archivist(self, workspace: Path) -> None:
        """Without an archivist, returns empty list."""
        llm = FakeLLMClient()
        curator = CuratorAgent(
            llm_client=llm,
            workspace_root=workspace,
        )
        proposals = curator.generate_proposals()
        assert proposals == []

    def test_low_connectivity_proposal(
        self,
        workspace: Path,
        archivist: Archivist,
        embedding_client: FakeEmbeddingClient,
    ) -> None:
        """Low graph density should generate a connectivity proposal."""
        # Create 4+ articles with no links between them
        topics = [
            ("alpha", "Alpha", "Alpha topic content about something."),
            ("beta", "Beta", "Beta topic content about something else."),
            ("gamma", "Gamma", "Gamma topic about another thing entirely."),
            ("delta", "Delta", "Delta topic about a fourth subject."),
        ]
        for slug, title, content in topics:
            rel_path = f"wiki/concepts/{slug}.md"
            full = f"---\ntitle: {title}\ntype: concept\n---\n\n{content}"
            path = workspace / rel_path
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(full)
            archivist.index_with_embeddings(rel_path, embedding_client=embedding_client)

        llm = FakeLLMClient()
        curator = CuratorAgent(
            llm_client=llm,
            workspace_root=workspace,
            archivist=archivist,
            embedding_client=embedding_client,
        )
        proposals = curator.generate_proposals()
        connectivity = [p for p in proposals if p["type"] == "low_connectivity"]
        assert len(connectivity) == 1
        assert "density" in connectivity[0]["reason"]
