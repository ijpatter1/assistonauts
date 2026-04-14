"""Tests for expedition CLI commands."""

from pathlib import Path

import yaml
from click.testing import CliRunner

from assistonauts.cli.main import cli


class TestExpeditionCreateCLI:
    def test_create_from_config_file(self, tmp_path: Path) -> None:
        runner = CliRunner()
        workspace = tmp_path / "workspace"

        # Initialize workspace
        result = runner.invoke(cli, ["init", str(workspace)])
        assert result.exit_code == 0

        # Write expedition config
        config_file = tmp_path / "expedition.yaml"
        config_file.write_text(
            yaml.dump(
                {
                    "expedition": {
                        "name": "test-exp",
                        "description": "Test expedition",
                        "purpose": "Test purpose for CLI",
                        "scope": {
                            "description": "Test",
                            "keywords": ["test"],
                        },
                    },
                }
            ),
        )

        result = runner.invoke(
            cli,
            [
                "expedition",
                "create",
                "--config",
                str(config_file),
                "-w",
                str(workspace),
            ],
        )
        assert result.exit_code == 0
        assert "test-exp" in result.output

        exp_dir = workspace / "expeditions" / "test-exp"
        assert exp_dir.exists()
        assert (exp_dir / "expedition.yaml").exists()
        assert (exp_dir / "missions").is_dir()
        assert (exp_dir / "review").is_dir()

    def test_create_already_exists(self, tmp_path: Path) -> None:
        runner = CliRunner()
        workspace = tmp_path / "workspace"
        runner.invoke(cli, ["init", str(workspace)])

        config_file = tmp_path / "expedition.yaml"
        config_file.write_text(
            yaml.dump(
                {
                    "expedition": {
                        "name": "dup",
                        "description": "Dup",
                        "purpose": "Test purpose for dup check",
                    },
                }
            ),
        )

        # First create succeeds
        runner.invoke(
            cli,
            [
                "expedition",
                "create",
                "--config",
                str(config_file),
                "-w",
                str(workspace),
            ],
        )
        # Second create fails gracefully
        result = runner.invoke(
            cli,
            [
                "expedition",
                "create",
                "--config",
                str(config_file),
                "-w",
                str(workspace),
            ],
        )
        assert result.exit_code == 0
        assert "already exists" in result.output.lower()


class TestBuildCLI:
    def test_build_no_expedition(self, tmp_path: Path) -> None:
        runner = CliRunner()
        workspace = tmp_path / "workspace"
        runner.invoke(cli, ["init", str(workspace)])

        result = runner.invoke(
            cli,
            ["build", "nonexistent", "-w", str(workspace)],
        )
        assert result.exit_code == 0
        assert "not found" in result.output.lower()

    def test_build_help(self) -> None:
        runner = CliRunner()
        result = runner.invoke(cli, ["build", "--help"])
        assert result.exit_code == 0
        assert "expedition" in result.output.lower()
