"""Scout CLI subcommands."""

from pathlib import Path

import click
from rich.console import Console

console = Console()


@click.group()
def scout() -> None:
    """Scout agent commands — ingest source material."""


@scout.command()
@click.argument("path", type=click.Path(exists=True, path_type=Path))
@click.option(
    "--category",
    "-c",
    default="articles",
    help="Category subdirectory in raw/ (default: articles)",
)
@click.option(
    "--workspace",
    "-w",
    default=".",
    type=click.Path(path_type=Path),
    help="Workspace root (default: current directory)",
)
def ingest(path: Path, category: str, workspace: Path) -> None:
    """Ingest a source file into the knowledge base."""
    from assistonauts.agents.scout import ScoutAgent
    from assistonauts.llm.client import LLMClient

    workspace = workspace.resolve()

    # Check workspace is initialized
    if not (workspace / "raw").is_dir():
        console.print(
            "[red]Error:[/red] Not an Assistonauts workspace. "
            "Run `assistonauts init` first."
        )
        raise SystemExit(1)

    # Create a minimal LLM client (Scout mostly uses toolkit, not LLM)
    llm_client = LLMClient(provider_config={}, mode="live")

    agent = ScoutAgent(
        llm_client=llm_client,
        workspace_root=workspace,
    )

    result = agent.ingest(path.resolve(), category=category)

    if result.skipped:
        console.print(f"[yellow]⊘[/yellow] Skipped [bold]{path}[/bold] (unchanged)")
    elif result.success:
        console.print(
            f"[green]✓[/green] Ingested [bold]{path}[/bold] → {result.manifest_key}"
        )
    else:
        console.print(f"[red]✗[/red] Failed: {result.message}")
        raise SystemExit(1)
