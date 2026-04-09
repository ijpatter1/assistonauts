"""CLI command for build phase execution."""

from pathlib import Path

import click
import yaml
from rich.console import Console

from assistonauts.expeditions.orchestrator import BuildOrchestrator
from assistonauts.models.config import ExpeditionConfig

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

    # Load expedition config
    config_path = exp_dir / "expedition.yaml"
    if not config_path.exists():
        console.print(
            f"[red]No expedition.yaml found in {exp_dir}[/red]",
        )
        return

    data = yaml.safe_load(config_path.read_text())
    config = ExpeditionConfig.from_dict(
        data.get("expedition", data),
    )

    console.print(
        f"[bold]Build phase:[/bold] {expedition_name}\n"
        f"Scope: {config.scope.description}\n",
    )

    # Resolve LLM client using existing pattern
    try:
        from assistonauts.config.loader import load_config
        from assistonauts.config.resolver import resolve_llm_for_role
        from assistonauts.llm.client import LLMClient

        app_config = load_config(workspace)
        model, base_url = resolve_llm_for_role(app_config, "captain")
        llm_client = LLMClient(
            provider_config={},
            mode="live",
            default_model=model,
            base_url=base_url,
        )
    except Exception as exc:
        console.print(
            f"[red]Failed to initialize LLM client:[/red] {exc}\n"
            "Check .assistonauts/config.yaml",
        )
        return

    orchestrator = BuildOrchestrator(
        workspace_root=workspace,
        config=config,
        llm_client=llm_client,
    )

    console.print("Running build phase (Discovery → Structuring → Refinement)...\n")

    try:
        result = orchestrator.run_build()
    except Exception as exc:
        console.print(
            f"[red]Build failed:[/red] {exc}\n"
            "Check LLM provider configuration and API keys.",
        )
        return

    console.print(
        f"\n[bold]Build complete:[/bold] "
        f"{result.total_completed}/{result.total_missions} missions completed, "
        f"{result.total_failed} failed\n",
    )

    for iteration in result.iterations:
        status = "done" if iteration.is_complete() else "partial"
        label = iteration.phase.value
        if iteration.missions_planned == 0:
            label += " (no missions planned)"
        console.print(
            f"  {label}: "
            f"{iteration.missions_completed}/{iteration.missions_planned} "
            f"({status})",
        )
        if iteration.budget_halt_message:
            console.print(
                f"  [yellow]{iteration.budget_halt_message}[/yellow]",
            )
