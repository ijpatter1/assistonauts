"""CLI command: assistonauts status — knowledge base overview."""

from __future__ import annotations

from pathlib import Path

import click
from rich.console import Console
from rich.table import Table

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
def status(workspace: Path) -> None:
    """Show expedition and knowledge base status overview."""
    workspace = workspace.resolve()

    if not (workspace / ".assistonauts").exists():
        console.print(f"[red]Error:[/red] Workspace not found at {workspace}")
        raise SystemExit(1)

    # Count wiki articles on disk
    wiki_dir = workspace / "wiki"
    articles_on_disk: list[Path] = []
    if wiki_dir.exists():
        articles_on_disk = list(wiki_dir.rglob("*.md"))

    # Count raw sources
    raw_dir = workspace / "raw"
    raw_files: list[Path] = []
    if raw_dir.exists():
        raw_files = list(raw_dir.rglob("*.md"))

    # Check index status
    db_path = workspace / "index" / "assistonauts.db"
    indexed_count = 0
    total_words = 0
    if db_path.exists():
        archivist = Archivist(workspace)
        indexed_articles = archivist.db.list_articles()
        indexed_count = len(indexed_articles)
        total_words = sum(int(a.get("word_count", 0)) for a in indexed_articles)

    # Display status
    table = Table(title="Knowledge Base Status", show_header=False)
    table.add_column("Metric", style="bold")
    table.add_column("Value", justify="right")

    table.add_row("Wiki articles on disk", str(len(articles_on_disk)))
    table.add_row("Raw sources", str(len(raw_files)))
    table.add_row("Indexed articles", str(indexed_count))
    table.add_row("Total words (indexed)", f"{total_words:,}")

    # Staleness check
    stale_count = 0
    if db_path.exists():
        for article in indexed_articles:
            path = str(article["path"])
            staleness = archivist.get_staleness(path)
            if staleness["is_stale"]:
                stale_count += 1
        table.add_row("Stale articles", str(stale_count))

    console.print(table)
