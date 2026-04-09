"""Tests for StructuredLogger persistence — .jsonl files created for all agents."""

from __future__ import annotations

import json
from pathlib import Path

from assistonauts.agents.explorer import ExplorerAgent
from assistonauts.agents.scout import ScoutAgent
from assistonauts.archivist.service import Archivist
from tests.helpers import FakeEmbeddingClient, FakeLLMClient


class TestLoggerPersistence:
    def test_scout_creates_log_dir(self, tmp_path: Path) -> None:
        """Scout should create the persistent log directory."""
        ws = tmp_path / "ws"
        ws.mkdir()
        (ws / "raw" / "articles").mkdir(parents=True)
        (ws / "index").mkdir(parents=True)
        (ws / "index" / "manifest.json").write_text("{}\n")

        ScoutAgent(llm_client=FakeLLMClient(), workspace_root=ws)
        log_dir = ws / ".assistonauts" / "logs"
        assert log_dir.exists()

    def test_explorer_creates_log_dir(self, tmp_path: Path) -> None:
        """Explorer should create the persistent log directory."""
        ws = tmp_path / "ws"
        ws.mkdir()
        (ws / "wiki" / "explorations").mkdir(parents=True)
        (ws / "wiki" / "concept").mkdir(parents=True)
        (ws / "index").mkdir(parents=True)

        embedding = FakeEmbeddingClient(dimensions=4)
        archivist = Archivist(ws, embedding_dimensions=4)
        ExplorerAgent(
            llm_client=FakeLLMClient(),
            workspace_root=ws,
            archivist=archivist,
            embedding_client=embedding,
        )
        log_dir = ws / ".assistonauts" / "logs"
        assert log_dir.exists()

    def test_log_file_receives_entries_on_llm_call(self, tmp_path: Path) -> None:
        """LLM calls should produce log entries in the .jsonl file."""
        ws = tmp_path / "ws"
        ws.mkdir()
        (ws / "wiki" / "explorations").mkdir(parents=True)
        (ws / "wiki" / "concept").mkdir(parents=True)
        (ws / "index").mkdir(parents=True)

        article = ws / "wiki" / "concept" / "test.md"
        article.write_text(
            "---\ntitle: Test\ntype: concept\nsources:\n- s.md\n"
            "created_at: 2026-01-01\n---\n\n## Overview\n\nContent.\n"
        )

        embedding = FakeEmbeddingClient(dimensions=4)
        archivist = Archivist(ws, embedding_dimensions=4)
        archivist.index_with_embeddings("wiki/concept/test.md", embedding)

        agent = ExplorerAgent(
            llm_client=FakeLLMClient(responses=["An answer."]),
            workspace_root=ws,
            archivist=archivist,
            embedding_client=embedding,
        )
        agent.explore("A question?")

        log_file = ws / ".assistonauts" / "logs" / "explorer.jsonl"
        lines = [line for line in log_file.read_text().splitlines() if line.strip()]
        assert len(lines) >= 1

        entry = json.loads(lines[0])
        assert entry["event"] == "llm_call"
        assert entry["role"] == "explorer"
        assert "prompt_tokens" in entry
