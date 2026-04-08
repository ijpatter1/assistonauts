"""CLI command: assistonauts index — index wiki articles into the Archivist."""

from __future__ import annotations

from pathlib import Path

import click
from rich.console import Console

from assistonauts.archivist.service import Archivist

console = Console()


@click.command()
@click.option(
    "-w",
    "--workspace",
    default=".",
    type=click.Path(path_type=Path),
    help="Workspace root directory.",
)
@click.option(
    "--reindex",
    is_flag=True,
    default=False,
    help="Force reindexing of all articles, even if unchanged.",
)
def index(workspace: Path, reindex: bool) -> None:
    """Index all wiki articles into the Archivist (FTS + metadata)."""
    workspace = workspace.resolve()

    if not (workspace / ".assistonauts").exists():
        console.print(f"[red]Error:[/red] Workspace not found at {workspace}")
        raise SystemExit(1)

    wiki_dir = workspace / "wiki"
    if not wiki_dir.exists():
        console.print("[yellow]No wiki directory found.[/yellow]")
        console.print("Indexed: 0, Skipped: 0")
        return

    # Collect all wiki articles
    articles = sorted(wiki_dir.rglob("*.md"))
    if not articles:
        console.print("No wiki articles found.")
        console.print("Indexed: 0, Skipped: 0")
        return

    archivist = Archivist(workspace)

    indexed = 0
    skipped = 0
    for article_path in articles:
        rel_path = str(article_path.relative_to(workspace))

        if reindex:
            # Delete existing entry to force reindex
            existing = archivist.db.get_article(rel_path)
            if existing:
                archivist.db.delete_article(rel_path)

        changed = archivist.index(rel_path)
        if changed:
            indexed += 1
            console.print(f"  [green]indexed[/green] {rel_path}")
        else:
            skipped += 1

    console.print(
        f"\n[bold]Indexed: {indexed}[/bold], "
        f"[dim]Skipped: {skipped}[/dim] "
        f"(total: {indexed + skipped} articles)"
    )
