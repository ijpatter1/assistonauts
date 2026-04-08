"""Tests for retroactive cross-referencing — Curator batch over all articles."""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from assistonauts.agents.curator import CuratorAgent
from assistonauts.archivist.embeddings import EmbeddingClient
from assistonauts.archivist.service import Archivist
from tests.helpers import FakeLLMClient


class FakeEmbeddingClient(EmbeddingClient):
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


@pytest.fixture
def workspace(initialized_workspace: Path) -> Path:
    return initialized_workspace


@pytest.fixture
def archivist(workspace: Path) -> Archivist:
    return Archivist(workspace, embedding_dimensions=4)


@pytest.fixture
def embedding_client() -> FakeEmbeddingClient:
    return FakeEmbeddingClient(dimensions=4)


def _populate_articles(
    workspace: Path,
    archivist: Archivist,
    embedding_client: FakeEmbeddingClient,
) -> list[str]:
    """Create and index several test articles."""
    articles = {
        "wiki/concepts/spectral.md": (
            "---\ntitle: Spectral Analysis\ntype: concept\n---\n\n"
            "Spectral analysis decomposes signals."
        ),
        "wiki/concepts/frequency.md": (
            "---\ntitle: Frequency Domain\ntype: concept\n---\n\n"
            "Frequency domain analysis of signals."
        ),
        "wiki/concepts/neural.md": (
            "---\ntitle: Neural Networks\ntype: concept\n---\n\n"
            "Neural networks for pattern recognition."
        ),
    }
    paths = []
    for rel_path, content in articles.items():
        full = workspace / rel_path
        full.parent.mkdir(parents=True, exist_ok=True)
        full.write_text(content)
        archivist.index_with_embeddings(rel_path, embedding_client=embedding_client)
        paths.append(rel_path)
    return paths


class TestRetroactiveCrossReferencing:
    """Test batch cross-referencing of all indexed articles."""

    def test_retroactive_xref_runs(
        self,
        workspace: Path,
        archivist: Archivist,
        embedding_client: FakeEmbeddingClient,
    ) -> None:
        paths = _populate_articles(workspace, archivist, embedding_client)
        llm = FakeLLMClient(responses=["## See Also\n\n- [[frequency]]"] * len(paths))
        curator = CuratorAgent(
            llm_client=llm,
            workspace_root=workspace,
            archivist=archivist,
            embedding_client=embedding_client,
        )
        results = curator.retroactive_cross_reference()
        assert len(results) == len(paths)
        assert all(r.success for r in results)

    def test_retroactive_xref_empty_kb(
        self,
        workspace: Path,
        archivist: Archivist,
        embedding_client: FakeEmbeddingClient,
    ) -> None:
        llm = FakeLLMClient()
        curator = CuratorAgent(
            llm_client=llm,
            workspace_root=workspace,
            archivist=archivist,
            embedding_client=embedding_client,
        )
        results = curator.retroactive_cross_reference()
        assert results == []
