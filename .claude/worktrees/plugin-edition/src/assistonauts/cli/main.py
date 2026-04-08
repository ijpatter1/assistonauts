"""Assistonauts CLI entry point."""

from pathlib import Path

import click
from rich.console import Console

from assistonauts.cli.mission import mission
from assistonauts.cli.scout import scout
from assistonauts.storage.workspace import init_workspace

console = Console()


@click.group()
@click.version_option(package_name="assistonauts")
def cli() -> None:
    """Assistonauts — LLM-powered knowledge base framework."""


cli.add_command(scout)
cli.add_command(mission)


@cli.command()
@click.argument("path", default=".", type=click.Path(path_type=Path))
def init(path: Path) -> None:
    """Initialize an Assistonauts workspace."""
    root = path.resolve()
    init_workspace(root)
    console.print(f"[green]✓[/green] Workspace initialized at [bold]{root}[/bold]")
