"""CLI command: assistonauts plan — editorial triage for compilation."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
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
    With --execute, compiles all proposed articles via the task runner.
    Plans are saved to .assistonauts/plans/ for audit trail.
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

    batch_size = 15
    num_batches = (len(sources) + batch_size - 1) // batch_size
    console.print(
        f"Analyzing {len(sources)} source files "
        f"({num_batches} batches of {batch_size})..."
    )

    llm_client = _create_llm_client(workspace, "compiler")
    compiler = CompilerAgent(llm_client=llm_client, workspace_root=workspace)

    compilation_plan = compiler.plan(sources, batch_size=batch_size)

    if not compilation_plan.articles:
        console.print("[yellow]No articles proposed.[/yellow]")
        return

    # Persist the plan
    plans_dir = workspace / ".assistonauts" / "plans"
    plan_path = compilation_plan.save(plans_dir)
    console.print(f"[dim]Plan saved: {plan_path.name}[/dim]")

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
        f"\n[bold]{len(compilation_plan.articles)} articles proposed"
        f"[/bold] from {len(sources)} sources."
    )

    if not execute:
        console.print(
            "\n[dim]Run with --execute to compile all proposed articles.[/dim]"
        )
        return

    # Execute the plan via task runner
    from assistonauts.tasks.runner import Task, TaskRunner

    tasks_dir = workspace / ".assistonauts" / "tasks"
    runner = TaskRunner(
        workspace_root=workspace,
        tasks_dir=tasks_dir,
    )

    console.print("\nCompiling via task runner...")
    executed_task_ids: list[str] = []
    for article in compilation_plan.articles:
        task_id = f"t-{uuid.uuid4().hex[:8]}"
        task = Task(
            task_id=task_id,
            agent="compiler",
            params={
                "source_paths": ",".join(str(p) for p in article.source_paths),
                "article_type": article.article_type.value,
                "title": article.title,
            },
        )
        result = runner.run(task, llm_client=llm_client)
        executed_task_ids.append(task_id)
        if result.success:
            output = ""
            if result.agent_output and result.agent_output.output_path:
                output = f" → {result.agent_output.output_path}"
            console.print(f"  [green]done[/green] [{task_id}] {article.title}{output}")
        else:
            console.print(
                f"  [red]failed[/red] [{task_id}] "
                f"{article.title}: {result.error_message}"
            )

    # Append task IDs to the plan artifact for traceability
    if executed_task_ids:
        _append_task_ids_to_plan(plan_path, executed_task_ids)

    console.print(f"\n[bold]Compiled {len(compilation_plan.articles)} articles.[/bold]")
    console.print(f"[dim]Plan: {plan_path.name}[/dim]")
    console.print(f"[dim]Task audit trails: {tasks_dir}/[/dim]")


def _append_task_ids_to_plan(plan_path: Path, task_ids: list[str]) -> None:
    """Append executed task IDs to an existing plan YAML file."""
    import yaml

    data = yaml.safe_load(plan_path.read_text())
    data["executed_at"] = datetime.now(UTC).isoformat()
    data["task_ids"] = task_ids
    plan_path.write_text(yaml.dump(data, default_flow_style=False))
