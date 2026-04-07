"""Smoke test — verifies the package is importable and CLI is registered."""

from click.testing import CliRunner

from assistonauts import __version__
from assistonauts.cli.main import cli


def test_version_is_set() -> None:
    assert __version__ == "0.1.0"


def test_cli_help() -> None:
    runner = CliRunner()
    result = runner.invoke(cli, ["--help"])
    assert result.exit_code == 0
    assert "Assistonauts" in result.output


def test_cli_version() -> None:
    runner = CliRunner()
    result = runner.invoke(cli, ["--version"])
    assert result.exit_code == 0
    assert "0.1.0" in result.output
