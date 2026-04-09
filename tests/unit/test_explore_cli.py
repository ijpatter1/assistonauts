"""Tests for the explore CLI command and interactive REPL."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest
from click.testing import CliRunner

from assistonauts.cli.main import cli


@pytest.fixture()
def workspace(tmp_path: Path) -> Path:
    """Create a workspace with indexed articles for CLI testing."""
    ws = tmp_path / "workspace"
    ws.mkdir()
    (ws / ".assistonauts").mkdir()
    (ws / "raw" / "articles").mkdir(parents=True)
    (ws / "wiki" / "concept").mkdir(parents=True)
    (ws / "wiki" / "explorations").mkdir(parents=True)
    (ws / "index").mkdir(parents=True)

    # Write default config
    config = ws / ".assistonauts" / "config.yaml"
    config.write_text(
        "llm:\n"
        "  default:\n"
        "    model: fake/model\n"
        "embedding:\n"
        "  active: ollama\n"
        "  providers:\n"
        "    ollama:\n"
        "      model: nomic-embed-text\n"
    )

    # Create article
    article = ws / "wiki" / "concept" / "neural-networks.md"
    article.write_text(
        "---\ntitle: Neural Networks\ntype: concept\nsources:\n- paper.pdf\n"
        "created_at: 2026-01-01\n---\n\n## Overview\n\nNeural networks.\n\n"
        "## Key Concepts\n\nLayers.\n\n## Sources\n\n- paper.pdf\n"
    )
    summary = ws / "wiki" / "concept" / "neural-networks.summary.json"
    summary.write_text(json.dumps({"summary": "Neural networks overview"}))

    # Index the article
    from tests.helpers import FakeEmbeddingClient

    from assistonauts.archivist.service import Archivist

    embedding = FakeEmbeddingClient(dimensions=4)
    archivist = Archivist(ws, embedding_dimensions=4)
    archivist.index_with_embeddings("wiki/concept/neural-networks.md", embedding)

    return ws


class TestExploreCLI:
    def test_explore_command_exists(self) -> None:
        """explore command should be registered in the CLI."""
        runner = CliRunner()
        result = runner.invoke(cli, ["explore", "--help"])
        assert result.exit_code == 0
        assert "explore" in result.output.lower() or "Explorer" in result.output

    def test_explore_requires_workspace(self, tmp_path: Path) -> None:
        """explore should fail if no workspace found."""
        runner = CliRunner()
        result = runner.invoke(cli, ["explore", "-w", str(tmp_path)])
        assert result.exit_code != 0

    def test_explore_single_query_mode(self, workspace: Path) -> None:
        """explore --query should answer a single question and exit."""
        runner = CliRunner()
        with (
            patch("assistonauts.cli.explore._create_embedding_client") as mock_emb,
            patch("assistonauts.cli.explore._create_llm_client") as mock_llm,
        ):
            from tests.helpers import FakeEmbeddingClient, FakeLLMClient

            mock_emb.return_value = FakeEmbeddingClient(dimensions=4)
            mock_llm.return_value = FakeLLMClient(
                responses=["Neural networks are great."]
            )

            result = runner.invoke(
                cli,
                [
                    "explore",
                    "-w",
                    str(workspace),
                    "--query",
                    "What are neural networks?",
                ],
            )
            assert result.exit_code == 0
            assert "neural" in result.output.lower() or "Neural" in result.output

    def test_explore_save_flag(self, workspace: Path) -> None:
        """explore --query --save should file the exploration."""
        runner = CliRunner()
        with (
            patch("assistonauts.cli.explore._create_embedding_client") as mock_emb,
            patch("assistonauts.cli.explore._create_llm_client") as mock_llm,
        ):
            from tests.helpers import FakeEmbeddingClient, FakeLLMClient

            mock_emb.return_value = FakeEmbeddingClient(dimensions=4)
            mock_llm.return_value = FakeLLMClient(
                responses=["Neural networks are great."]
            )

            result = runner.invoke(
                cli,
                [
                    "explore",
                    "-w",
                    str(workspace),
                    "--query",
                    "What are neural networks?",
                    "--save",
                ],
            )
            assert result.exit_code == 0

            # Check that an exploration file was created
            explorations = list((workspace / "wiki" / "explorations").glob("*.md"))
            assert len(explorations) >= 1

    def test_interactive_mode_quit(self, workspace: Path) -> None:
        """Interactive mode should exit on /quit."""
        runner = CliRunner()
        with (
            patch("assistonauts.cli.explore._create_embedding_client") as mock_emb,
            patch("assistonauts.cli.explore._create_llm_client") as mock_llm,
        ):
            from tests.helpers import FakeEmbeddingClient, FakeLLMClient

            mock_emb.return_value = FakeEmbeddingClient(dimensions=4)
            mock_llm.return_value = FakeLLMClient(responses=["An answer."])

            result = runner.invoke(
                cli,
                ["explore", "-w", str(workspace)],
                input="/quit\n",
            )
            assert result.exit_code == 0

    def test_interactive_mode_ask_and_quit(self, workspace: Path) -> None:
        """Interactive mode should answer a question then quit."""
        runner = CliRunner()
        with (
            patch("assistonauts.cli.explore._create_embedding_client") as mock_emb,
            patch("assistonauts.cli.explore._create_llm_client") as mock_llm,
        ):
            from tests.helpers import FakeEmbeddingClient, FakeLLMClient

            mock_emb.return_value = FakeEmbeddingClient(dimensions=4)
            mock_llm.return_value = FakeLLMClient(
                responses=["Neural networks are computing systems."]
            )

            result = runner.invoke(
                cli,
                ["explore", "-w", str(workspace)],
                input="What are neural networks?\n/quit\n",
            )
            assert result.exit_code == 0
