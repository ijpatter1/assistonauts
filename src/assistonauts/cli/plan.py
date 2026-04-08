"""CLI command: assistonauts plan — editorial triage for compilation."""

from __future__ import annotations

from pathlib import Path

import click
from rich.console import Console
from rich.table import Table

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
    "--execute",
    is_flag=True,
    default=False,
    help="Execute the plan immediately after showing it.",
)
def plan(workspace: Path, execute: bool) -> None:
    """Analyze raw sources and propose a compilation plan.

    Reads all raw/articles/*.md files, asks the Compiler to propose
    article groupings, types, and titles. Shows the plan for review.
    With --execute, compiles all proposed articles after showing the plan.
    """
    from assistonauts.agents.compiler import CompilerAgent
    from assistonauts.cli.task import _create_llm_client

    workspace = workspace.resolve()

    if not (workspace / ".assistonauts").exists():
        console.print(f"[red]Error:[/red] Workspace not found at {workspace}")
        raise SystemExit(1)

    raw_dir = workspace / "raw" / "articles"
    if not raw_dir.exists():
        console.print("[yellow]No raw/articles/ directory found.[/yellow]")
        return

    sources = sorted(raw_dir.glob("*.md"))
    if not sources:
        console.print("No raw source files found in raw/articles/.")
        return

    console.print(f"Analyzing {len(sources)} source files...")

    llm_client = _create_llm_client(workspace, "compiler")
    compiler = CompilerAgent(llm_client=llm_client, workspace_root=workspace)

    compilation_plan = compiler.plan(sources)

    if not compilation_plan.articles:
        console.print("[yellow]No articles proposed.[/yellow]")
        return

    # Display the plan
    table = Table(title="Compilation Plan")
    table.add_column("Article", style="bold")
    table.add_column("Type")
    table.add_column("Sources")
    table.add_column("Rationale", max_width=40)

    for article in compilation_plan.articles:
        source_names = ", ".join(p.name for p in article.source_paths)
        table.add_row(
            article.title,
            article.article_type.value,
            source_names,
            article.rationale,
        )

    console.print(table)
    console.print(
        f"\n[bold]{len(compilation_plan.articles)} articles proposed[/bold] "
        f"from {len(sources)} sources."
    )

    if not execute:
        console.print(
            "\n[dim]Run with --execute to compile all proposed articles.[/dim]"
        )
        return

    # Execute the plan
    console.print("\nCompiling...")
    for article in compilation_plan.articles:
        console.print(
            f"  Compiling [bold]{article.title}[/bold] "
            f"({article.article_type.value})..."
        )
        result = compiler.compile_multi(
            source_paths=article.source_paths,
            article_type=article.article_type,
            title=article.title,
        )
        if result.success:
            console.print(f"    [green]done[/green] → {result.manifest_key}")
        else:
            console.print(f"    [red]failed[/red] {result.message}")

    console.print(f"\n[bold]Compiled {len(compilation_plan.articles)} articles.[/bold]")
