"""CLI command: assistonauts index — index wiki articles into the Archivist."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import click
from rich.console import Console

from assistonauts.archivist.service import Archivist

if TYPE_CHECKING:
    from assistonauts.archivist.embeddings import EmbeddingClient

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
@click.option(
    "--embeddings/--no-embeddings",
    default=True,
    help="Generate vector embeddings (requires embedding model). Default: on.",
)
def index(workspace: Path, reindex: bool, embeddings: bool) -> None:
    """Index all wiki articles into the Archivist (FTS + embeddings)."""
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

    # Load config for embedding dimensions
    from assistonauts.archivist.embeddings import get_embedding_dimensions
    from assistonauts.config.loader import load_config

    config = load_config(workspace)
    dims = get_embedding_dimensions(config.embedding)
    archivist = Archivist(workspace, embedding_dimensions=dims)

    # Set up embedding client if requested
    embedding_client = None
    if embeddings:
        embedding_client = _create_embedding_client(workspace)
        if embedding_client is None:
            console.print(
                "[yellow]Warning:[/yellow] Could not initialize "
                "embedding model. Indexing FTS only."
            )

    indexed = 0
    skipped = 0
    summaries_loaded = 0
    for article_path in articles:
        rel_path = str(article_path.relative_to(workspace))

        if reindex:
            existing = archivist.db.get_article(rel_path)
            if existing:
                archivist.db.delete_article(rel_path)

        if embedding_client is not None:
            try:
                changed = archivist.index_with_embeddings(
                    rel_path, embedding_client=embedding_client
                )
            except Exception as exc:
                console.print(
                    f"[yellow]Warning:[/yellow] Embedding failed ({exc!r}). "
                    "Falling back to FTS only."
                )
                embedding_client = None
                changed = archivist.index(rel_path)
        else:
            changed = archivist.index(rel_path)

        if changed:
            indexed += 1
            console.print(f"  [green]indexed[/green] {rel_path}")
            # Check if summary was loaded
            summary_path = article_path.with_suffix(".summary.json")
            if summary_path.exists():
                summaries_loaded += 1
                console.print("    [cyan]summary loaded[/cyan]")
        else:
            skipped += 1

    mode = "FTS + embeddings" if embedding_client else "FTS only"
    summary_info = f", Summaries: {summaries_loaded}" if summaries_loaded else ""
    console.print(
        f"\n[bold]Indexed: {indexed}[/bold], "
        f"[dim]Skipped: {skipped}[/dim]{summary_info} "
        f"(total: {indexed + skipped} articles, {mode})"
    )


def _create_embedding_client(
    workspace: Path,
) -> EmbeddingClient | None:
    """Try to create an embedding client from workspace config."""
    from assistonauts.archivist.embeddings import create_embedding_client
    from assistonauts.config.loader import load_config

    try:
        config = load_config(workspace)
        return create_embedding_client(config.embedding)
    except Exception:
        return None
