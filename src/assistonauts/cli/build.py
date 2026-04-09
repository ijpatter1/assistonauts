"""CLI command for build phase execution."""

from pathlib import Path

import click
from rich.console import Console

console = Console()


@click.command()
@click.argument("expedition_name")
@click.option(
    "-w",
    "--workspace",
    type=click.Path(path_type=Path),
    default=".",
    help="Workspace root directory.",
)
def build(expedition_name: str, workspace: Path) -> None:
    """Run the build phase for an expedition."""
    workspace = workspace.resolve()
    exp_dir = workspace / "expeditions" / expedition_name

    if not exp_dir.exists():
        console.print(
            f"[red]Expedition not found:[/red] {expedition_name}\n"
            f"Expected at: {exp_dir}\n"
            "Create it first with: assistonauts expedition create "
            "--config <path>",
        )
        return

    console.print(
        f"[bold]Build phase:[/bold] {expedition_name}\n"
        f"Expedition dir: {exp_dir}\n\n"
        "[yellow]Build orchestration not yet implemented — "
        "requires iterative planning (Deliverable 3).[/yellow]",
    )
