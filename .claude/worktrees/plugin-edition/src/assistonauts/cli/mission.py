"""Mission CLI subcommands."""

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
def mission() -> None:
    """Mission commands — execute agent missions."""


@mission.command()
@click.option(
    "--agent",
    "-a",
    required=True,
    type=click.Choice(["compiler", "scout"]),
    help="Agent to run the mission with.",
)
@click.option(
    "--source",
    "-s",
    required=True,
    help="Path to the source file to process.",
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
    help="Auto-commit after successful mission.",
)
def run(
    agent: str,
    source: str,
    title: str,
    article_type: str,
    workspace: Path,
    commit: bool,
) -> None:
    """Execute a single agent mission."""
    from assistonauts.missions.runner import Mission, MissionRunner

    workspace = workspace.resolve()

    # Check workspace is initialized
    if not (workspace / "raw").is_dir():
        console.print(
            "[red]Error:[/red] Not an Assistonauts workspace. "
            "Run `assistonauts init` first."
        )
        raise SystemExit(1)

    source_path = Path(source).resolve()
    if not title:
        title = source_path.stem.replace("-", " ").replace("_", " ").title()

    mission_id = f"m-{uuid.uuid4().hex[:8]}"
    missions_dir = workspace / ".assistonauts" / "missions"
    missions_dir.mkdir(parents=True, exist_ok=True)

    llm_client = _create_llm_client(workspace, agent)

    runner = MissionRunner(
        workspace_root=workspace,
        missions_dir=missions_dir,
        auto_commit=commit,
    )

    mission_obj = Mission(
        mission_id=mission_id,
        agent=agent,
        params={
            "source_path": str(source_path),
            "article_type": article_type,
            "title": title,
        },
    )

    try:
        result = runner.run(mission_obj, llm_client=llm_client)

        if result.success:
            console.print(
                f"[green]✓[/green] Completed mission "
                f"[bold]{mission_id}[/bold] ({agent})"
            )
            if result.agent_output and result.agent_output.output_path:
                console.print(f"  Output: {result.agent_output.output_path}")
        else:
            console.print(
                f"[red]✗[/red] Mission {mission_id} failed: {result.error_message}"
            )
            raise SystemExit(1)
    except SystemExit:
        raise
    except Exception as exc:
        console.print(f"[red]Error:[/red] {exc}")
        raise SystemExit(1) from exc
