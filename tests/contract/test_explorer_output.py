"""Contract tests for Explorer agent output structure.

These tests validate the structural contracts of Explorer output:
- ExplorerResult has required fields populated
- Answer text is non-empty and references article titles
- Citations reference real articles from the knowledge base
- Formatted answer includes sources section when citations exist
- Context budget is respected
- Filed explorations have valid YAML frontmatter and required sections

Uses recorded LLM fixtures for deterministic, fast execution.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

from assistonauts.agents.explorer import ExplorerAgent, ExplorerResult
from assistonauts.archivist.service import Archivist
from assistonauts.tools.explorer import Citation
from tests.helpers import FakeEmbeddingClient, FakeLLMClient

_FIXTURES_DIR = Path(__file__).parent.parent / "fixtures" / "explorer"


class FixtureLLMClient(FakeLLMClient):
    """LLM client that loads responses from fixture files on disk."""

    def __init__(self, fixture_names: list[str]) -> None:
        responses: list[str] = []
        for name in fixture_names:
            fixture_path = _FIXTURES_DIR / f"{name}.json"
            data = json.loads(fixture_path.read_text())
            responses.append(data["content"])
        super().__init__(responses=responses)


@pytest.fixture()
def workspace(tmp_path: Path) -> Path:
    """Create workspace with indexed wiki articles."""
    from assistonauts.storage.workspace import init_workspace

    root = init_workspace(tmp_path)
    concept_dir = root / "wiki" / "concept"
    concept_dir.mkdir(parents=True, exist_ok=True)
    (root / "wiki" / "explorations").mkdir(parents=True, exist_ok=True)

    # Article A
    article_a = concept_dir / "ml-fundamentals.md"
    article_a.write_text(
        "---\n"
        "title: Machine Learning Fundamentals\n"
        "type: concept\n"
        "sources:\n"
        "  - ml-basics.md\n"
        "created_at: 2026-01-15\n"
        "compiled_by: compiler\n"
        "status: draft\n"
        "---\n\n"
        "## Overview\n\n"
        "Machine learning is a branch of AI that learns from data.\n\n"
        "## Key Concepts\n\n"
        "Supervised learning, unsupervised learning, reinforcement learning.\n\n"
        "## Sources\n\n"
        "- ml-basics.md\n"
    )
    summary_a = concept_dir / "ml-fundamentals.summary.json"
    summary_a.write_text(json.dumps({"summary": "ML overview and key concepts"}))

    # Article B
    article_b = concept_dir / "backpropagation.md"
    article_b.write_text(
        "---\n"
        "title: Backpropagation\n"
        "type: concept\n"
        "sources:\n"
        "  - textbook.pdf\n"
        "created_at: 2026-01-16\n"
        "compiled_by: compiler\n"
        "status: draft\n"
        "---\n\n"
        "## Overview\n\n"
        "Backpropagation computes gradients for training neural networks.\n\n"
        "## Key Concepts\n\n"
        "Chain rule, gradient descent, loss functions.\n\n"
        "## Sources\n\n"
        "- textbook.pdf\n"
    )
    summary_b = concept_dir / "backpropagation.summary.json"
    summary_b.write_text(json.dumps({"summary": "Backpropagation algorithm"}))

    # Index articles
    embedding = FakeEmbeddingClient(dimensions=4)
    archivist = Archivist(root, embedding_dimensions=4)
    archivist.index_with_embeddings("wiki/concept/ml-fundamentals.md", embedding)
    archivist.index_with_embeddings("wiki/concept/backpropagation.md", embedding)

    return root


@pytest.fixture()
def explorer_result(workspace: Path) -> ExplorerResult:
    """Run an exploration using recorded fixture and return the result."""
    llm = FixtureLLMClient(["explore_answer"])
    embedding = FakeEmbeddingClient(dimensions=4)
    archivist = Archivist(workspace, embedding_dimensions=4)

    explorer = ExplorerAgent(
        llm_client=llm,
        workspace_root=workspace,
        archivist=archivist,
        embedding_client=embedding,
    )
    return explorer.explore("What is machine learning?")


class TestExplorerOutputContract:
    """Contract tests: Explorer output must conform to structural requirements."""

    def test_result_is_successful(self, explorer_result: ExplorerResult) -> None:
        """Explorer result must report success."""
        assert explorer_result.success is True

    def test_result_has_non_empty_answer(self, explorer_result: ExplorerResult) -> None:
        """Answer text must be non-empty."""
        assert explorer_result.answer
        assert len(explorer_result.answer) > 20

    def test_result_records_query(self, explorer_result: ExplorerResult) -> None:
        """Result must record the original query string."""
        assert explorer_result.query == "What is machine learning?"

    def test_result_has_citations(self, explorer_result: ExplorerResult) -> None:
        """Result must include at least one citation."""
        assert len(explorer_result.citations) > 0

    def test_citations_are_citation_objects(
        self, explorer_result: ExplorerResult
    ) -> None:
        """Each citation must be a Citation dataclass with required fields."""
        for citation in explorer_result.citations:
            assert isinstance(citation, Citation)
            assert citation.title
            assert citation.path
            assert citation.path.endswith(".md")

    def test_citations_reference_real_articles(
        self, explorer_result: ExplorerResult, workspace: Path
    ) -> None:
        """Citations must reference articles that exist on disk."""
        for citation in explorer_result.citations:
            full_path = workspace / citation.path
            assert full_path.exists(), f"Citation path not found: {citation.path}"

    def test_formatted_answer_includes_sources(
        self, explorer_result: ExplorerResult
    ) -> None:
        """Formatted answer must include a Sources section."""
        assert "## Sources" in explorer_result.formatted_answer

    def test_formatted_answer_includes_query(
        self, explorer_result: ExplorerResult
    ) -> None:
        """Formatted answer must include the original query."""
        assert "What is machine learning?" in explorer_result.formatted_answer

    def test_context_budget_is_tracked(self, explorer_result: ExplorerResult) -> None:
        """Result must report context token usage."""
        assert explorer_result.context_tokens_used >= 0

    def test_retrieval_metadata_populated(
        self, explorer_result: ExplorerResult
    ) -> None:
        """Result must report articles retrieved and used."""
        assert explorer_result.articles_retrieved >= 0
        assert explorer_result.articles_used >= 0
        assert explorer_result.articles_used <= explorer_result.articles_retrieved


class TestExplorerFilingContract:
    """Contract tests: filed explorations must conform to article schema."""

    def test_filed_exploration_has_valid_frontmatter(
        self, explorer_result: ExplorerResult, workspace: Path
    ) -> None:
        """Filed exploration must have parseable YAML frontmatter."""
        llm = FakeLLMClient(responses=["unused"])
        embedding = FakeEmbeddingClient(dimensions=4)
        archivist = Archivist(workspace, embedding_dimensions=4)
        explorer = ExplorerAgent(
            llm_client=llm,
            workspace_root=workspace,
            archivist=archivist,
            embedding_client=embedding,
        )
        path = explorer.file_exploration(explorer_result)
        content = path.read_text()

        assert content.startswith("---\n")
        # Extract and parse frontmatter
        end = content.find("---", 3)
        assert end != -1
        frontmatter = yaml.safe_load(content[3:end])
        assert isinstance(frontmatter, dict)

    def test_filed_exploration_frontmatter_has_required_fields(
        self, explorer_result: ExplorerResult, workspace: Path
    ) -> None:
        """Frontmatter must contain title, type, sources, created_at, status."""
        llm = FakeLLMClient(responses=["unused"])
        embedding = FakeEmbeddingClient(dimensions=4)
        archivist = Archivist(workspace, embedding_dimensions=4)
        explorer = ExplorerAgent(
            llm_client=llm,
            workspace_root=workspace,
            archivist=archivist,
            embedding_client=embedding,
        )
        path = explorer.file_exploration(explorer_result)
        content = path.read_text()
        end = content.find("---", 3)
        frontmatter = yaml.safe_load(content[3:end])

        assert frontmatter["title"] == "What is machine learning?"
        assert frontmatter["type"] == "exploration"
        assert "sources" in frontmatter
        assert "created_at" in frontmatter
        assert frontmatter["status"] == "exploration"

    def test_filed_exploration_has_required_sections(
        self, explorer_result: ExplorerResult, workspace: Path
    ) -> None:
        """Filed exploration must have Question, Analysis, and Sources sections."""
        llm = FakeLLMClient(responses=["unused"])
        embedding = FakeEmbeddingClient(dimensions=4)
        archivist = Archivist(workspace, embedding_dimensions=4)
        explorer = ExplorerAgent(
            llm_client=llm,
            workspace_root=workspace,
            archivist=archivist,
            embedding_client=embedding,
        )
        path = explorer.file_exploration(explorer_result)
        content = path.read_text()

        assert "## Question" in content
        assert "## Analysis" in content
        assert "## Findings" in content
        assert "## Open Questions" in content
        assert "## Sources" in content

    def test_filed_exploration_in_explorations_dir(
        self, explorer_result: ExplorerResult, workspace: Path
    ) -> None:
        """Filed exploration must be saved to wiki/explorations/."""
        llm = FakeLLMClient(responses=["unused"])
        embedding = FakeEmbeddingClient(dimensions=4)
        archivist = Archivist(workspace, embedding_dimensions=4)
        explorer = ExplorerAgent(
            llm_client=llm,
            workspace_root=workspace,
            archivist=archivist,
            embedding_client=embedding,
        )
        path = explorer.file_exploration(explorer_result)

        expected_dir = workspace / "wiki" / "explorations"
        assert path.parent == expected_dir
