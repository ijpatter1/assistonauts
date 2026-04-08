"""Tests for the `assistonauts status` CLI command."""

from __future__ import annotations

from pathlib import Path

from click.testing import CliRunner

from assistonauts.cli.main import cli
from assistonauts.storage.workspace import init_workspace


class TestStatusCommand:
    """Test the status CLI command."""

    def test_status_no_workspace(self, tmp_path: Path) -> None:
        runner = CliRunner()
        result = runner.invoke(cli, ["status", "-w", str(tmp_path / "nope")])
        assert result.exit_code != 0 or "not found" in result.output.lower()

    def test_status_empty_workspace(self, tmp_path: Path) -> None:
        init_workspace(tmp_path)
        runner = CliRunner()
        result = runner.invoke(cli, ["status", "-w", str(tmp_path)])
        assert result.exit_code == 0
        assert "articles" in result.output.lower()

    def test_status_with_articles(self, tmp_path: Path) -> None:
        init_workspace(tmp_path)
        # Write a wiki article
        article = tmp_path / "wiki" / "concepts" / "test.md"
        article.parent.mkdir(parents=True, exist_ok=True)
        article.write_text("---\ntitle: Test\ntype: concept\n---\n\nContent.")
        runner = CliRunner()
        result = runner.invoke(cli, ["status", "-w", str(tmp_path)])
        assert result.exit_code == 0
        # Should show article count
        assert "1" in result.output

    def test_status_shows_indexed_count(self, tmp_path: Path) -> None:
        init_workspace(tmp_path)
        runner = CliRunner()
        result = runner.invoke(cli, ["status", "-w", str(tmp_path)])
        assert result.exit_code == 0
        assert "indexed" in result.output.lower()
