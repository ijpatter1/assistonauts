"""Tests for `assistonauts index` and `assistonauts curate` CLI commands."""

from __future__ import annotations

from pathlib import Path

import pytest
from click.testing import CliRunner

from assistonauts.cli.main import cli
from assistonauts.storage.workspace import init_workspace


def _write_article(workspace: Path, rel_path: str, content: str) -> None:
    full = workspace / rel_path
    full.parent.mkdir(parents=True, exist_ok=True)
    full.write_text(content)


_ARTICLE = """\
---
title: Test Article
type: concept
---

# Test Article

This is a test article about spectral analysis.
"""


class TestIndexCommand:
    """Test the `assistonauts index` CLI command."""

    def test_index_no_workspace(self, tmp_path: Path) -> None:
        runner = CliRunner()
        result = runner.invoke(cli, ["index", "-w", str(tmp_path / "nope")])
        assert result.exit_code != 0

    def test_index_empty_workspace(self, tmp_path: Path) -> None:
        init_workspace(tmp_path)
        runner = CliRunner()
        result = runner.invoke(cli, ["index", "-w", str(tmp_path)])
        assert result.exit_code == 0
        assert "0" in result.output  # 0 articles indexed

    def test_index_with_articles(self, tmp_path: Path) -> None:
        init_workspace(tmp_path)
        _write_article(tmp_path, "wiki/concepts/test.md", _ARTICLE)
        runner = CliRunner()
        result = runner.invoke(cli, ["index", "-w", str(tmp_path)])
        assert result.exit_code == 0
        assert "indexed" in result.output.lower()

    def test_index_skips_unchanged(self, tmp_path: Path) -> None:
        init_workspace(tmp_path)
        _write_article(tmp_path, "wiki/concepts/test.md", _ARTICLE)
        runner = CliRunner()
        # Index twice
        runner.invoke(cli, ["index", "-w", str(tmp_path)])
        result = runner.invoke(cli, ["index", "-w", str(tmp_path)])
        assert result.exit_code == 0
        assert "skipped" in result.output.lower()

    def test_index_reindex_flag(self, tmp_path: Path) -> None:
        init_workspace(tmp_path)
        _write_article(tmp_path, "wiki/concepts/test.md", _ARTICLE)
        runner = CliRunner()
        runner.invoke(cli, ["index", "-w", str(tmp_path)])
        result = runner.invoke(cli, ["index", "-w", str(tmp_path), "--reindex"])
        assert result.exit_code == 0
        # With --reindex, should re-index even if unchanged
        assert "indexed" in result.output.lower()


class TestCurateCommand:
    """Test the `assistonauts curate` CLI command."""

    def test_curate_no_workspace(self, tmp_path: Path) -> None:
        runner = CliRunner()
        result = runner.invoke(cli, ["curate", "-w", str(tmp_path / "nope")])
        assert result.exit_code != 0

    def test_curate_empty_workspace(self, tmp_path: Path) -> None:
        init_workspace(tmp_path)
        runner = CliRunner()
        result = runner.invoke(cli, ["curate", "-w", str(tmp_path)])
        assert result.exit_code == 0

    def test_curate_proposals_flag(self, tmp_path: Path) -> None:
        init_workspace(tmp_path)
        runner = CliRunner()
        result = runner.invoke(cli, ["curate", "-w", str(tmp_path), "--proposals"])
        assert result.exit_code == 0
        assert "proposal" in result.output.lower()

    def test_curate_runs_cross_referencing(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Curate without --proposals invokes retroactive_cross_reference."""
        import assistonauts.cli.curate as curate_mod

        init_workspace(tmp_path)

        # Track whether cross-referencing was called
        xref_called = False

        class FakeCurator:
            def retroactive_cross_reference(self) -> list[object]:
                nonlocal xref_called
                xref_called = True
                return []

            def close(self) -> None:
                pass

        class FakeArchivist:
            class db:
                @staticmethod
                def list_articles() -> list[dict[str, str]]:
                    return [{"path": "wiki/concepts/test.md"}]

        monkeypatch.setattr(
            curate_mod,
            "_create_curator",
            lambda workspace: FakeCurator(),
        )
        monkeypatch.setattr(
            curate_mod,
            "Archivist",
            lambda workspace: FakeArchivist(),
        )

        runner = CliRunner()
        result = runner.invoke(cli, ["curate", "-w", str(tmp_path)])
        assert result.exit_code == 0, result.output
        assert xref_called, "curate should invoke retroactive_cross_reference"
