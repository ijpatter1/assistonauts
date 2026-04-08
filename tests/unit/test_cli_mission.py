"""Tests for the mission CLI command."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from click.testing import CliRunner

from assistonauts.cli.main import cli


class FakeResponse:
    def __init__(self, content: str) -> None:
        self.content = content
        self.model = "fake-model"
        self.usage = {"prompt_tokens": 10, "completion_tokens": 5}


_FAKE_ARTICLE = (
    "---\ntitle: Test\ntype: concept\n---\n\n# Test\n\n## Overview\n\nContent."
)


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
    missions_dir = root / ".assistonauts" / "missions"
    missions_dir.mkdir(parents=True, exist_ok=True)
    return root


class TestMissionCLI:
    """Test the mission run CLI command."""

    def test_mission_run_compiler_success(self, tmp_path: Path) -> None:
        workspace = _make_workspace(tmp_path)
        source = workspace / "raw" / "articles" / "test-source.md"

        runner = CliRunner()
        with patch("assistonauts.cli.mission._create_llm_client") as mock_llm:
            fake_llm = _FakeLLMClient()
            mock_llm.return_value = fake_llm
            result = runner.invoke(
                cli,
                [
                    "mission",
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
        assert "Completed" in result.output or "✓" in result.output

    def test_mission_run_missing_source(self, tmp_path: Path) -> None:
        workspace = _make_workspace(tmp_path)
        runner = CliRunner()
        with patch("assistonauts.cli.mission._create_llm_client") as mock_llm:
            mock_llm.return_value = _FakeLLMClient()
            result = runner.invoke(
                cli,
                [
                    "mission",
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

    def test_mission_run_not_workspace(self, tmp_path: Path) -> None:
        runner = CliRunner()
        result = runner.invoke(
            cli,
            [
                "mission",
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

    def test_mission_run_writes_audit_file(self, tmp_path: Path) -> None:
        workspace = _make_workspace(tmp_path)
        source = workspace / "raw" / "articles" / "test-source.md"

        runner = CliRunner()
        with patch("assistonauts.cli.mission._create_llm_client") as mock_llm:
            mock_llm.return_value = _FakeLLMClient()
            runner.invoke(
                cli,
                [
                    "mission",
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
        missions_dir = workspace / ".assistonauts" / "missions"
        yaml_files = list(missions_dir.glob("*.yaml"))
        assert len(yaml_files) > 0


class _FakeLLMClient:
    """Fake LLM for CLI tests."""

    def __init__(self) -> None:
        self._call_count = 0

    def complete(
        self,
        messages: list[dict[str, str]],
        model: str | None = None,
        system: str | None = None,
        **kwargs: object,
    ) -> FakeResponse:
        self._call_count += 1
        if self._call_count == 1:
            return FakeResponse(_FAKE_ARTICLE)
        return FakeResponse("Summary of compiled article.")
