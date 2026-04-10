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
@click.option(
    "--dry-run",
    is_flag=True,
    default=False,
    help="Show Discovery plan without executing missions.",
)
def build(expedition_name: str, workspace: Path, dry_run: bool) -> None:
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

    # Enable orchestrator logging to console for progress feedback
    import logging

    orch_logger = logging.getLogger("assistonauts.expeditions.orchestrator")
    if not orch_logger.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter("  %(message)s"))
        orch_logger.addHandler(handler)
        orch_logger.setLevel(logging.INFO)

    if dry_run:
        console.print("[bold]Dry run:[/bold] planning Discovery only...\n")
    else:
        console.print(
            "Running build phase (Discovery → Structuring → Refinement)...\n",
        )

    try:
        result = orchestrator.run_build(dry_run=dry_run)
    except Exception as exc:
        console.print(
            f"[red]Build failed:[/red] {exc}\n"
            "Check LLM provider configuration and API keys.",
        )
        return

    if dry_run:
        console.print(
            f"\n[bold]Dry run complete:[/bold] "
            f"{result.total_missions} missions planned "
            f"(not executed)\n",
        )
        for iteration in result.iterations:
            console.print(
                f"  {iteration.phase.value}: "
                f"{iteration.missions_planned} missions planned",
            )
            for m in iteration.missions:
                inputs_brief = ", ".join(f"{k}={v}" for k, v in m.inputs.items())
                console.print(
                    f"    [{m.mission_id}] {m.agent}/{m.mission_type}"
                    f" — {inputs_brief or 'no inputs'}",
                )
        console.print(
            f"\nPlan written to expeditions/{expedition_name}/plan.yaml",
        )
        return

    if result.total_missions == 0:
        console.print(
            "\n[yellow]Warning:[/yellow] Build produced no missions. "
            "The Captain's LLM responses could not be parsed into "
            "valid mission plans. Check LLM configuration and model "
            "quality.\n",
        )

    console.print(
        f"\n[bold]Build complete:[/bold] "
        f"{result.total_completed}/{result.total_missions} missions "
        f"completed, {result.total_failed} failed\n",
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

    console.print(
        f"\nBuild report: expeditions/{expedition_name}/build-report.md",
    )
