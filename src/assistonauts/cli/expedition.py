"""CLI commands for expedition management."""

from pathlib import Path

import click
from rich.console import Console

from assistonauts.expeditions.lifecycle import create_expedition_from_file

console = Console()


@click.group()
def expedition() -> None:
    """Manage expeditions."""


@expedition.command()
@click.option(
    "--config",
    "config_path",
    required=True,
    type=click.Path(exists=True, path_type=Path),
    help="Path to expedition YAML config file.",
)
@click.option(
    "-w",
    "--workspace",
    type=click.Path(path_type=Path),
    default=".",
    help="Workspace root directory.",
)
def create(config_path: Path, workspace: Path) -> None:
    """Create a new expedition from a config file."""
    workspace = workspace.resolve()
    try:
        exp_dir = create_expedition_from_file(config_path, workspace)
        console.print(
            f"[green]\\u2713[/green] Expedition created at [bold]{exp_dir}[/bold]",
        )
    except FileExistsError as e:
        console.print(f"[yellow]Already exists:[/yellow] {e}")
