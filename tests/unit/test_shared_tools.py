"""Tests for shared toolkit functions."""

import json
from pathlib import Path

from assistonauts.tools.shared import StructuredLogger


class TestStructuredLogger:
    """Test structured logging to JSON-lines files."""

    def test_creates_log_file(self, tmp_path: Path) -> None:
        """Logger creates a .jsonl log file in the log directory."""
        logger = StructuredLogger(role="scout", log_dir=tmp_path)
        logger.log("test_event")

        log_files = list(tmp_path.glob("*.jsonl"))
        assert len(log_files) == 1
        assert "scout" in log_files[0].name

    def test_log_entry_has_required_fields(self, tmp_path: Path) -> None:
        """Each log entry has timestamp, role, and event."""
        logger = StructuredLogger(role="scout", log_dir=tmp_path)
        logger.log("test_event", detail="value")

        log_file = tmp_path / "scout.jsonl"
        entry = json.loads(log_file.read_text().strip())
        assert "timestamp" in entry
        assert entry["role"] == "scout"
        assert entry["event"] == "test_event"
        assert entry["detail"] == "value"

    def test_log_with_mission_id(self, tmp_path: Path) -> None:
        """Mission ID is included in log entries when provided."""
        logger = StructuredLogger(role="scout", log_dir=tmp_path, mission_id="m-001")
        logger.log("ingest")

        log_file = tmp_path / "scout_m-001.jsonl"
        assert log_file.exists()
        entry = json.loads(log_file.read_text().strip())
        assert entry["mission_id"] == "m-001"

    def test_log_llm_call(self, tmp_path: Path) -> None:
        """log_llm_call records model and token counts."""
        logger = StructuredLogger(role="compiler", log_dir=tmp_path)
        logger.log_llm_call(
            model="claude-sonnet-4-20250514",
            prompt_tokens=100,
            completion_tokens=50,
        )

        log_file = tmp_path / "compiler.jsonl"
        entry = json.loads(log_file.read_text().strip())
        assert entry["event"] == "llm_call"
        assert entry["model"] == "claude-sonnet-4-20250514"
        assert entry["prompt_tokens"] == 100
        assert entry["completion_tokens"] == 50

    def test_log_tool_invoke(self, tmp_path: Path) -> None:
        """log_tool_invoke records the tool name."""
        logger = StructuredLogger(role="scout", log_dir=tmp_path)
        logger.log_tool_invoke("hash_content", path="/tmp/doc.md")

        log_file = tmp_path / "scout.jsonl"
        entry = json.loads(log_file.read_text().strip())
        assert entry["event"] == "tool_invoke"
        assert entry["tool_name"] == "hash_content"

    def test_multiple_entries_appended(self, tmp_path: Path) -> None:
        """Multiple log calls append to the same file."""
        logger = StructuredLogger(role="scout", log_dir=tmp_path)
        logger.log("event1")
        logger.log("event2")
        logger.log("event3")

        log_file = tmp_path / "scout.jsonl"
        lines = log_file.read_text().strip().split("\n")
        assert len(lines) == 3

    def test_no_log_dir_does_not_error(self) -> None:
        """Logger without log_dir still works (logs to Python logger only)."""
        logger = StructuredLogger(role="scout")
        logger.log("test_event")  # Should not raise
