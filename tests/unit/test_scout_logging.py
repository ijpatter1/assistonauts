"""Tests for Scout ingest logging — conversion and skip decisions."""

from __future__ import annotations

import json
from pathlib import Path

from assistonauts.agents.scout import ScoutAgent
from tests.helpers import FakeLLMClient


class TestScoutLogging:
    def test_document_conversion_logged(self, tmp_path: Path) -> None:
        """Ingesting a markdown file should log a document_conversion event."""
        ws = tmp_path / "ws"
        ws.mkdir()
        (ws / "raw" / "articles").mkdir(parents=True)
        (ws / "index").mkdir(parents=True)
        (ws / "index" / "manifest.json").write_text("{}\n")

        source = tmp_path / "test.md"
        source.write_text("# Test\n\nSome content here.")

        agent = ScoutAgent(llm_client=FakeLLMClient(), workspace_root=ws)
        agent.ingest(source)

        log_file = ws / ".assistonauts" / "logs" / "scout.jsonl"
        assert log_file.exists()
        entries = [
            json.loads(line)
            for line in log_file.read_text().splitlines()
            if line.strip()
        ]

        conversion_entries = [e for e in entries if e["event"] == "document_conversion"]
        assert len(conversion_entries) == 1
        assert conversion_entries[0]["source"] == "test.md"
        assert conversion_entries[0]["output_chars"] > 0

    def test_skip_logged(self, tmp_path: Path) -> None:
        """Skipping an unchanged file should log an ingest_skipped event."""
        ws = tmp_path / "ws"
        ws.mkdir()
        (ws / "raw" / "articles").mkdir(parents=True)
        (ws / "index").mkdir(parents=True)
        (ws / "index" / "manifest.json").write_text("{}\n")

        source = tmp_path / "test.md"
        source.write_text("# Test\n\nContent.")

        agent = ScoutAgent(llm_client=FakeLLMClient(), workspace_root=ws)
        agent.ingest(source)  # First ingest
        agent.ingest(source)  # Second ingest — should skip

        log_file = ws / ".assistonauts" / "logs" / "scout.jsonl"
        entries = [
            json.loads(line)
            for line in log_file.read_text().splitlines()
            if line.strip()
        ]

        skip_entries = [e for e in entries if e["event"] == "ingest_skipped"]
        assert len(skip_entries) == 1
        assert skip_entries[0]["source"] == "test.md"
        assert skip_entries[0]["reason"] == "content_unchanged"

    def test_log_includes_source_bytes(self, tmp_path: Path) -> None:
        """Conversion log should include the source file size."""
        ws = tmp_path / "ws"
        ws.mkdir()
        (ws / "raw" / "articles").mkdir(parents=True)
        (ws / "index").mkdir(parents=True)
        (ws / "index" / "manifest.json").write_text("{}\n")

        source = tmp_path / "doc.md"
        source.write_text("# Document\n\n" + "word " * 500)

        agent = ScoutAgent(llm_client=FakeLLMClient(), workspace_root=ws)
        agent.ingest(source)

        log_file = ws / ".assistonauts" / "logs" / "scout.jsonl"
        entries = [
            json.loads(line)
            for line in log_file.read_text().splitlines()
            if line.strip()
        ]

        conversion = next(e for e in entries if e["event"] == "document_conversion")
        assert conversion["source_bytes"] > 0
