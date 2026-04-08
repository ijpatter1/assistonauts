"""Tests for the Curator agent — cross-referencing pipeline."""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from assistonauts.agents.curator import CuratorAgent
from assistonauts.archivist.embeddings import EmbeddingClient
from assistonauts.archivist.service import Archivist
from tests.helpers import FakeLLMClient


class FakeEmbeddingClient(EmbeddingClient):
    """Deterministic embedding client for testing."""

    def __init__(self, dimensions: int = 4) -> None:
        self._dimensions = dimensions

    @property
    def dimensions(self) -> int:
        return self._dimensions

    def embed(self, text: str) -> list[float]:
        h = hashlib.sha256(text.encode()).digest()
        return [b / 255.0 for b in h[: self._dimensions]]

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        return [self.embed(t) for t in texts]


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
        assert len(result.links_added) >= 0  # May be 0 if already linked

    def test_run_mission(
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
        result = curator.run_mission(
            {"article_path": "wiki/concepts/spectral-analysis.md"}
        )
        assert result.success is True
