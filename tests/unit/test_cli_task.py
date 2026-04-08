"""Tests for the task CLI command."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from click.testing import CliRunner

from assistonauts.cli.main import cli
from tests.helpers import FakeLLMClient

_FAKE_ARTICLE = (
    "---\ntitle: Test\ntype: concept\n---\n\n# Test\n\n## Overview\n\nContent."
)
_FAKE_SUMMARY = "Summary of compiled article."
_COMPILER_RESPONSES = [_FAKE_ARTICLE, _FAKE_SUMMARY]


def _make_workspace(tmp_path: Path) -> Path:
    """Create a minimal initialized workspace."""
    from assistonauts.storage.workspace import init_workspace

    root = init_workspace(tmp_path)
    raw_dir = root / "raw" / "articles"
    raw_dir.mkdir(parents=True, exist_ok=True)
    source = raw_dir / "test-source.md"
    source.write_text(
        "---\nsource: test-source.md\n---\n\n# Test Content\n\nSome text.\n"
    )
    tasks_dir = root / ".assistonauts" / "tasks"
    tasks_dir.mkdir(parents=True, exist_ok=True)
    return root


class TestTaskCLI:
    """Test the task run CLI command."""

    def test_task_run_compiler_success(self, tmp_path: Path) -> None:
        workspace = _make_workspace(tmp_path)
        source = workspace / "raw" / "articles" / "test-source.md"

        runner = CliRunner()
        with patch("assistonauts.cli.task._create_llm_client") as mock_llm:
            fake_llm = FakeLLMClient(_COMPILER_RESPONSES)
            mock_llm.return_value = fake_llm
            result = runner.invoke(
                cli,
                [
                    "task",
                    "run",
                    "--agent",
                    "compiler",
                    "--source",
                    str(source),
                    "--title",
                    "Test Article",
                    "--workspace",
                    str(workspace),
                ],
            )
        assert result.exit_code == 0, result.output
        assert "Completed" in result.output or "\u2713" in result.output

    def test_task_run_missing_source(self, tmp_path: Path) -> None:
        workspace = _make_workspace(tmp_path)
        runner = CliRunner()
        with patch("assistonauts.cli.task._create_llm_client") as mock_llm:
            mock_llm.return_value = FakeLLMClient(_COMPILER_RESPONSES)
            result = runner.invoke(
                cli,
                [
                    "task",
                    "run",
                    "--agent",
                    "compiler",
                    "--source",
                    "/nonexistent/file.md",
                    "--title",
                    "Bad",
                    "--workspace",
                    str(workspace),
                ],
            )
        assert result.exit_code == 1

    def test_task_run_not_workspace(self, tmp_path: Path) -> None:
        runner = CliRunner()
        result = runner.invoke(
            cli,
            [
                "task",
                "run",
                "--agent",
                "compiler",
                "--source",
                "test.md",
                "--title",
                "Test",
                "--workspace",
                str(tmp_path),
            ],
        )
        assert result.exit_code == 1
        assert "workspace" in result.output.lower()

    def test_task_run_writes_audit_file(self, tmp_path: Path) -> None:
        workspace = _make_workspace(tmp_path)
        source = workspace / "raw" / "articles" / "test-source.md"

        runner = CliRunner()
        with patch("assistonauts.cli.task._create_llm_client") as mock_llm:
            mock_llm.return_value = FakeLLMClient(_COMPILER_RESPONSES)
            runner.invoke(
                cli,
                [
                    "task",
                    "run",
                    "--agent",
                    "compiler",
                    "--source",
                    str(source),
                    "--title",
                    "Test",
                    "--workspace",
                    str(workspace),
                ],
            )
        tasks_dir = workspace / ".assistonauts" / "tasks"
        yaml_files = list(tasks_dir.glob("*.yaml"))
        assert len(yaml_files) > 0
