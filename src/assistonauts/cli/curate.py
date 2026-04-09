"""CLI command: assistonauts curate — run Curator cross-referencing."""

from __future__ import annotations

from pathlib import Path

import click
from rich.console import Console

from assistonauts.archivist.service import Archivist

console = Console()


def _create_curator(workspace: Path) -> CuratorAgent:  # noqa: F821 — lazy import
    """Create a fully-wired CuratorAgent from workspace config.

    Loads LLM config, creates an Archivist + EmbeddingClient, and returns
    a CuratorAgent ready for cross-referencing.
    """
    from assistonauts.agents.curator import CuratorAgent
    from assistonauts.archivist.embeddings import LiteLLMEmbeddingClient
    from assistonauts.cli.task import _create_llm_client

    llm_client = _create_llm_client(workspace, "curator")
    archivist = Archivist(workspace)
    embedding_client = LiteLLMEmbeddingClient()

    return CuratorAgent(
        llm_client=llm_client,
        workspace_root=workspace,
        archivist=archivist,
        embedding_client=embedding_client,
    )


@click.command()
@click.option(
    "-w",
    "--workspace",
    default=".",
    type=click.Path(path_type=Path),
    help="Workspace root directory.",
)
@click.option(
    "--proposals",
    is_flag=True,
    default=False,
    help="Show structural improvement proposals instead of cross-referencing.",
)
def curate(workspace: Path, proposals: bool) -> None:
    """Run Curator cross-referencing over all indexed articles."""
    workspace = workspace.resolve()

    if not (workspace / ".assistonauts").exists():
        console.print(f"[red]Error:[/red] Workspace not found at {workspace}")
        raise SystemExit(1)

    archivist = Archivist(workspace)
    all_articles = archivist.db.list_articles()

    if proposals:
        _show_proposals(workspace, archivist)
        return

    if not all_articles:
        console.print("No indexed articles found. Run `assistonauts index` first.")
        return

    console.print(f"Cross-referencing {len(all_articles)} indexed articles...")

    curator = _create_curator(workspace)
    try:
        results = curator.retroactive_cross_reference()
        total_links = sum(len(r.links_added) for r in results)
        console.print(
            f"[green]Done.[/green] Processed {len(results)} articles, "
            f"added {total_links} cross-references."
        )
    finally:
        curator.close()


def _show_proposals(workspace: Path, archivist: Archivist) -> None:
    """Show structural proposals without requiring LLM."""
    from assistonauts.tools.curator import (
        analyze_graph,
        scan_backlink_targets,
    )

    wiki_dir = workspace / "wiki"
    all_articles = [str(a["path"]) for a in archivist.db.list_articles()]

    if not all_articles:
        console.print("No indexed articles. No proposals to generate.")
        return

    # Build link graph
    backlink_targets = scan_backlink_targets(wiki_dir)
    links: dict[str, list[str]] = {a: [] for a in all_articles}
    for bt in backlink_targets:
        try:
            rel = str(bt.source_path.relative_to(workspace))
        except ValueError:
            continue
        if rel in links:
            links[rel].append(bt.target_slug)

    metrics = analyze_graph(links, all_articles)

    console.print("\n[bold]Knowledge Graph Metrics[/bold]")
    console.print(f"  Articles: {metrics.total_articles}")
    console.print(f"  Links: {metrics.total_links}")
    console.print(f"  Density: {metrics.density:.3f}")
    console.print(f"  Orphans: {len(metrics.orphans)}")

    if metrics.orphans:
        console.print("\n[bold]Proposals:[/bold]")
        for orphan in metrics.orphans:
            console.print(
                f"  [yellow]orphan[/yellow] {orphan} — no incoming or outgoing links"
            )

    if metrics.density < 0.1 and metrics.total_articles > 3:
        console.print(
            f"  [yellow]low_connectivity[/yellow] "
            f"Graph density {metrics.density:.3f} — "
            "consider adding more cross-references"
        )

    if not metrics.orphans and not (
        metrics.density < 0.1 and metrics.total_articles > 3
    ):
        console.print("\n[green]No structural issues found.[/green]")
