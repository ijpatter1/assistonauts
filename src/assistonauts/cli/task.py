"""Task CLI subcommands."""

from __future__ import annotations

import uuid
from pathlib import Path

import click
from rich.console import Console

from assistonauts.llm.client import LLMClient

console = Console()


def _create_llm_client(
    workspace: Path,
    agent_role: str,
) -> LLMClient:
    """Create an LLM client configured from workspace config.

    Loads .assistonauts/config.yaml, resolves the provider for the
    agent role, and returns a client with the correct model and base_url.
    """
    from assistonauts.config.loader import load_config
    from assistonauts.config.resolver import resolve_llm_for_role

    config = load_config(workspace)
    model, base_url = resolve_llm_for_role(config, agent_role)
    return LLMClient(
        provider_config={},
        mode="live",
        default_model=model,
        base_url=base_url,
    )


@click.group()
def task() -> None:
    """Task commands — execute agent tasks."""


@task.command()
@click.option(
    "--agent",
    "-a",
    required=True,
    type=click.Choice(["compiler", "scout"]),
    help="Agent to run the task with.",
)
@click.option(
    "--source",
    "-s",
    required=True,
    multiple=True,
    help="Path to source file(s). Repeat for multi-source compilation.",
)
@click.option(
    "--title",
    "-t",
    default="",
    help="Article title (default: derived from filename).",
)
@click.option(
    "--article-type",
    default="concept",
    type=click.Choice(["concept", "entity", "log", "exploration"]),
    help="Article type (default: concept).",
)
@click.option(
    "--workspace",
    "-w",
    default=".",
    type=click.Path(path_type=Path),
    help="Workspace root (default: current directory).",
)
@click.option(
    "--commit/--no-commit",
    default=False,
    help="Auto-commit after successful task.",
)
def run(
    agent: str,
    source: tuple[str, ...],
    title: str,
    article_type: str,
    workspace: Path,
    commit: bool,
) -> None:
    """Execute a single agent task."""
    from assistonauts.tasks.runner import Task, TaskRunner

    workspace = workspace.resolve()

    # Check workspace is initialized
    if not (workspace / "raw").is_dir():
        console.print(
            "[red]Error:[/red] Not an Assistonauts workspace. "
            "Run `assistonauts init` first."
        )
        raise SystemExit(1)

    source_paths = [Path(s).resolve() for s in source]
    if not title:
        title = source_paths[0].stem.replace("-", " ").replace("_", " ").title()

    task_id = f"t-{uuid.uuid4().hex[:8]}"
    tasks_dir = workspace / ".assistonauts" / "tasks"
    tasks_dir.mkdir(parents=True, exist_ok=True)

    llm_client = _create_llm_client(workspace, agent)

    runner = TaskRunner(
        workspace_root=workspace,
        tasks_dir=tasks_dir,
        auto_commit=commit,
    )

    # Multi-source: pass comma-separated paths
    if len(source_paths) > 1:
        params = {
            "source_paths": ",".join(str(p) for p in source_paths),
            "article_type": article_type,
            "title": title,
        }
    else:
        params = {
            "source_path": str(source_paths[0]),
            "article_type": article_type,
            "title": title,
        }

    task_obj = Task(
        task_id=task_id,
        agent=agent,
        params=params,
    )

    try:
        result = runner.run(task_obj, llm_client=llm_client)

        if result.success:
            console.print(
                f"[green]\u2713[/green] Completed task [bold]{task_id}[/bold] ({agent})"
            )
            if result.agent_output and result.agent_output.output_path:
                console.print(f"  Output: {result.agent_output.output_path}")
        else:
            console.print(
                f"[red]\u2717[/red] Task {task_id} failed: {result.error_message}"
            )
            raise SystemExit(1)
    except SystemExit:
        raise
    except Exception as exc:
        console.print(f"[red]Error:[/red] {exc}")
        raise SystemExit(1) from exc
