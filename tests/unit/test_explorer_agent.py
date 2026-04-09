"""Tests for Explorer agent — query synthesis with citations."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from assistonauts.agents.explorer import ExplorerAgent, ExplorerResult
from assistonauts.archivist.service import Archivist
from tests.helpers import FakeEmbeddingClient, FakeLLMClient


@pytest.fixture()
def workspace(tmp_path: Path) -> Path:
    """Create a minimal workspace with indexed articles."""
    ws = tmp_path / "workspace"
    ws.mkdir()
    (ws / "raw" / "articles").mkdir(parents=True)
    (ws / "wiki" / "concept").mkdir(parents=True)
    (ws / "wiki" / "explorations").mkdir(parents=True)
    (ws / "index").mkdir(parents=True)

    # Create two wiki articles with frontmatter
    article_a = ws / "wiki" / "concept" / "neural-networks.md"
    article_a.write_text(
        "---\ntitle: Neural Networks\ntype: concept\nsources:\n- paper.pdf\n"
        "created_at: 2026-01-01\n---\n\n## Overview\n\nNeural networks are "
        "computing systems inspired by biological neural networks.\n\n"
        "## Key Concepts\n\nLayers, weights, activation functions.\n\n"
        "## Sources\n\n- paper.pdf\n"
    )
    summary_a = ws / "wiki" / "concept" / "neural-networks.summary.json"
    summary_a.write_text(json.dumps({"summary": "Neural networks overview"}))

    article_b = ws / "wiki" / "concept" / "backpropagation.md"
    article_b.write_text(
        "---\ntitle: Backpropagation\ntype: concept\nsources:\n- textbook.pdf\n"
        "created_at: 2026-01-02\n---\n\n## Overview\n\nBackpropagation is "
        "the algorithm used to train neural networks by computing gradients.\n\n"
        "## Key Concepts\n\nGradient descent, chain rule, loss function.\n\n"
        "## Sources\n\n- textbook.pdf\n"
    )
    summary_b = ws / "wiki" / "concept" / "backpropagation.summary.json"
    summary_b.write_text(json.dumps({"summary": "Backpropagation algorithm"}))

    return ws


@pytest.fixture()
def indexed_workspace(workspace: Path) -> Path:
    """Workspace with articles indexed in the Archivist DB."""
    embedding = FakeEmbeddingClient(dimensions=4)
    archivist = Archivist(workspace, embedding_dimensions=4)
    archivist.index_with_embeddings("wiki/concept/neural-networks.md", embedding)
    archivist.index_with_embeddings("wiki/concept/backpropagation.md", embedding)
    return workspace


class TestExplorerAgent:
    def test_explore_returns_result(self, indexed_workspace: Path) -> None:
        """Explorer.explore() returns an ExplorerResult."""
        llm = FakeLLMClient(
            responses=[
                "Neural networks are computing systems with layers and weights. "
                "Backpropagation trains them using gradient descent."
            ]
        )
        embedding = FakeEmbeddingClient(dimensions=4)
        archivist = Archivist(indexed_workspace, embedding_dimensions=4)

        explorer = ExplorerAgent(
            llm_client=llm,
            workspace_root=indexed_workspace,
            archivist=archivist,
            embedding_client=embedding,
        )
        result = explorer.explore("What are neural networks?")

        assert isinstance(result, ExplorerResult)
        assert result.success is True
        assert result.answer != ""

    def test_explore_includes_citations(self, indexed_workspace: Path) -> None:
        """Answer should include citations to retrieved articles."""
        llm = FakeLLMClient(
            responses=["Neural networks use backpropagation for training."]
        )
        embedding = FakeEmbeddingClient(dimensions=4)
        archivist = Archivist(indexed_workspace, embedding_dimensions=4)

        explorer = ExplorerAgent(
            llm_client=llm,
            workspace_root=indexed_workspace,
            archivist=archivist,
            embedding_client=embedding,
        )
        result = explorer.explore("How do neural networks learn?")

        assert len(result.citations) > 0
        # Citations should reference actual articles from the index
        citation_paths = [c.path for c in result.citations]
        assert any("neural-networks" in p for p in citation_paths)

    def test_explore_sends_article_context_to_llm(
        self, indexed_workspace: Path
    ) -> None:
        """LLM should receive article content as context."""
        llm = FakeLLMClient(responses=["Answer based on context."])
        embedding = FakeEmbeddingClient(dimensions=4)
        archivist = Archivist(indexed_workspace, embedding_dimensions=4)

        explorer = ExplorerAgent(
            llm_client=llm,
            workspace_root=indexed_workspace,
            archivist=archivist,
            embedding_client=embedding,
        )
        explorer.explore("What is backpropagation?")

        # Verify LLM was called with article content in the prompt
        assert len(llm.calls) == 1
        user_msg = llm.calls[0]["messages"][-1]["content"]
        assert "backpropagation" in user_msg.lower() or "neural" in user_msg.lower()

    def test_explore_respects_context_budget(self, indexed_workspace: Path) -> None:
        """Explorer should not exceed the context budget."""
        llm = FakeLLMClient(responses=["Short answer."])
        embedding = FakeEmbeddingClient(dimensions=4)
        archivist = Archivist(indexed_workspace, embedding_dimensions=4)

        explorer = ExplorerAgent(
            llm_client=llm,
            workspace_root=indexed_workspace,
            archivist=archivist,
            embedding_client=embedding,
            max_context_tokens=8000,
        )
        result = explorer.explore("Tell me everything")

        assert result.success is True
        assert result.context_tokens_used <= 8000

    def test_explore_with_empty_kb(self, workspace: Path) -> None:
        """Explorer should handle empty knowledge base gracefully."""
        llm = FakeLLMClient(responses=["I don't have enough information."])
        embedding = FakeEmbeddingClient(dimensions=4)
        archivist = Archivist(workspace, embedding_dimensions=4)

        explorer = ExplorerAgent(
            llm_client=llm,
            workspace_root=workspace,
            archivist=archivist,
            embedding_client=embedding,
        )
        result = explorer.explore("What is anything?")

        assert isinstance(result, ExplorerResult)
        assert result.success is True
        assert len(result.citations) == 0

    def test_explore_records_query(self, indexed_workspace: Path) -> None:
        """Result should record the original query."""
        llm = FakeLLMClient(responses=["An answer."])
        embedding = FakeEmbeddingClient(dimensions=4)
        archivist = Archivist(indexed_workspace, embedding_dimensions=4)

        explorer = ExplorerAgent(
            llm_client=llm,
            workspace_root=indexed_workspace,
            archivist=archivist,
            embedding_client=embedding,
        )
        result = explorer.explore("What are neural networks?")

        assert result.query == "What are neural networks?"

    def test_formatted_answer_includes_sources_section(
        self, indexed_workspace: Path
    ) -> None:
        """formatted_answer should include a Sources section with citations."""
        llm = FakeLLMClient(responses=["Neural networks are great."])
        embedding = FakeEmbeddingClient(dimensions=4)
        archivist = Archivist(indexed_workspace, embedding_dimensions=4)

        explorer = ExplorerAgent(
            llm_client=llm,
            workspace_root=indexed_workspace,
            archivist=archivist,
            embedding_client=embedding,
        )
        result = explorer.explore("What are neural networks?")

        assert "Sources" in result.formatted_answer or len(result.citations) == 0

    def test_explore_uses_system_prompt(self, indexed_workspace: Path) -> None:
        """Explorer should use its system prompt for LLM calls."""
        llm = FakeLLMClient(responses=["Response."])
        embedding = FakeEmbeddingClient(dimensions=4)
        archivist = Archivist(indexed_workspace, embedding_dimensions=4)

        explorer = ExplorerAgent(
            llm_client=llm,
            workspace_root=indexed_workspace,
            archivist=archivist,
            embedding_client=embedding,
        )
        explorer.explore("A question?")

        assert llm.calls[0]["system"] is not None
        assert "Explorer" in llm.calls[0]["system"]

    def test_result_has_retrieval_metadata(self, indexed_workspace: Path) -> None:
        """Result should include metadata about the retrieval process."""
        llm = FakeLLMClient(responses=["Answer."])
        embedding = FakeEmbeddingClient(dimensions=4)
        archivist = Archivist(indexed_workspace, embedding_dimensions=4)

        explorer = ExplorerAgent(
            llm_client=llm,
            workspace_root=indexed_workspace,
            archivist=archivist,
            embedding_client=embedding,
        )
        result = explorer.explore("Neural network question")

        assert result.articles_retrieved >= 0
        assert result.articles_used >= 0
        assert result.articles_used <= result.articles_retrieved
