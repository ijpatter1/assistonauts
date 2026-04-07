"""Tests for workspace initialization."""

from pathlib import Path

import pytest
from click.testing import CliRunner

from assistonauts.cli.main import cli
from assistonauts.storage.workspace import init_workspace


class TestInitWorkspace:
    """Test assistonauts init workspace creation."""

    def test_creates_top_level_directories(self, tmp_workspace: Path) -> None:
        """init creates all required top-level directories."""
        init_workspace(tmp_workspace)

        expected_dirs = [
            "raw",
            "wiki",
            "index",
            "audits",
            "expeditions",
            "station-logs",
            ".assistonauts",
        ]
        for d in expected_dirs:
            assert (tmp_workspace / d).is_dir(), f"Missing directory: {d}"

    def test_creates_raw_subdirectories(self, tmp_workspace: Path) -> None:
        """init creates raw/ subdirectories for source categories."""
        init_workspace(tmp_workspace)

        for sub in ["papers", "articles", "repos", "datasets", "assets"]:
            assert (tmp_workspace / "raw" / sub).is_dir(), f"Missing raw/{sub}"

    def test_creates_wiki_subdirectories(self, tmp_workspace: Path) -> None:
        """init creates wiki/ subdirectories for article types."""
        init_workspace(tmp_workspace)

        for sub in ["concepts", "entities", "logs", "explorations"]:
            assert (tmp_workspace / "wiki" / sub).is_dir(), f"Missing wiki/{sub}"

    def test_creates_audits_subdirectories(self, tmp_workspace: Path) -> None:
        """init creates audits/findings/ subdirectory."""
        init_workspace(tmp_workspace)

        assert (tmp_workspace / "audits" / "findings").is_dir()

    def test_creates_assistonauts_subdirectories(self, tmp_workspace: Path) -> None:
        """init creates .assistonauts/ subdirectories."""
        init_workspace(tmp_workspace)

        for sub in ["agents", "cache", "hooks"]:
            assert (tmp_workspace / ".assistonauts" / sub).is_dir()

    def test_creates_empty_manifest(self, tmp_workspace: Path) -> None:
        """init creates an empty manifest.json in index/."""
        init_workspace(tmp_workspace)

        manifest = tmp_workspace / "index" / "manifest.json"
        assert manifest.is_file()
        assert manifest.read_text() == "{}\n"

    def test_creates_default_config(self, tmp_workspace: Path) -> None:
        """init creates a default config.yaml in .assistonauts/."""
        init_workspace(tmp_workspace)

        config = tmp_workspace / ".assistonauts" / "config.yaml"
        assert config.is_file()
        content = config.read_text()
        assert "llm:" in content
        assert "roles:" in content

    def test_creates_gitignore(self, tmp_workspace: Path) -> None:
        """init creates .gitignore with expected patterns."""
        init_workspace(tmp_workspace)

        gitignore = tmp_workspace / ".gitignore"
        assert gitignore.is_file()
        content = gitignore.read_text()
        assert ".assistonauts/cache/" in content
        assert "index/assistonauts.db" in content
        assert "__pycache__/" in content
        assert ".env" in content

    def test_idempotent(self, tmp_workspace: Path) -> None:
        """Running init twice does not error or destroy existing content."""
        init_workspace(tmp_workspace)

        # Add a file to raw/
        test_file = tmp_workspace / "raw" / "papers" / "test.md"
        test_file.write_text("existing content")

        # Run init again
        init_workspace(tmp_workspace)

        # File should still exist
        assert test_file.read_text() == "existing content"

    def test_idempotent_preserves_manifest(self, tmp_workspace: Path) -> None:
        """Running init twice does not overwrite existing manifest."""
        init_workspace(tmp_workspace)

        manifest = tmp_workspace / "index" / "manifest.json"
        manifest.write_text('{"raw/test.md": {"hash": "abc123"}}\n')

        init_workspace(tmp_workspace)

        assert "abc123" in manifest.read_text()

    def test_idempotent_preserves_config(self, tmp_workspace: Path) -> None:
        """Running init twice does not overwrite existing config."""
        init_workspace(tmp_workspace)

        config = tmp_workspace / ".assistonauts" / "config.yaml"
        config.write_text("custom: true\n")

        init_workspace(tmp_workspace)

        assert config.read_text() == "custom: true\n"

    def test_initializes_git_repo(self, tmp_workspace: Path) -> None:
        """init creates a git repository."""
        init_workspace(tmp_workspace)
        assert (tmp_workspace / ".git").is_dir()

    def test_idempotent_git_repo(self, tmp_workspace: Path) -> None:
        """Running init twice does not break existing git repo."""
        init_workspace(tmp_workspace)
        init_workspace(tmp_workspace)
        assert (tmp_workspace / ".git").is_dir()

    def test_returns_workspace_path(self, tmp_workspace: Path) -> None:
        """init returns the workspace root path."""
        result = init_workspace(tmp_workspace)
        assert result == tmp_workspace


class TestInitCLI:
    """Test the `assistonauts init` CLI command."""

    def test_init_command_creates_workspace(self, tmp_path: Path) -> None:
        """CLI init creates workspace at the given path."""
        runner = CliRunner()
        target = tmp_path / "my-kb"
        target.mkdir()
        result = runner.invoke(cli, ["init", str(target)])
        assert result.exit_code == 0
        assert (target / "raw").is_dir()
        assert (target / "index" / "manifest.json").is_file()

    def test_init_command_default_cwd(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """CLI init defaults to current directory."""
        monkeypatch.chdir(tmp_path)
        runner = CliRunner()
        result = runner.invoke(cli, ["init"])
        assert result.exit_code == 0
        assert (tmp_path / "raw").is_dir()
