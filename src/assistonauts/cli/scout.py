"""Scout CLI subcommands."""

from pathlib import Path

import click
from rich.console import Console

console = Console()


def _is_url(value: str) -> bool:
    """Check if a string looks like a URL."""
    return value.startswith(("http://", "https://"))


@click.group()
def scout() -> None:
    """Scout agent commands — ingest source material."""


@scout.command()
@click.argument("source", nargs=-1, required=True)
@click.option(
    "--category",
    "-c",
    default="articles",
    help="Category subdirectory in raw/ (default: articles)",
)
@click.option(
    "--workspace",
    "-w",
    default=".",
    type=click.Path(path_type=Path),
    help="Workspace root (default: current directory)",
)
def ingest(source: tuple[str, ...], category: str, workspace: Path) -> None:
    """Ingest source file(s) or URL(s) into the knowledge base.

    Accepts multiple files: assistonauts scout ingest a.png b.png c.png
    """
    from assistonauts.agents.scout import ScoutAgent
    from assistonauts.config.loader import load_config
    from assistonauts.config.resolver import resolve_llm_for_role
    from assistonauts.llm.client import LLMClient
    from assistonauts.tools.scout import clip_web

    workspace = workspace.resolve()

    # Check workspace is initialized
    if not (workspace / "raw").is_dir():
        console.print(
            "[red]Error:[/red] Not an Assistonauts workspace. "
            "Run `assistonauts init` first."
        )
        raise SystemExit(1)

    # Create LLM client from workspace config (needed for image vision)
    config = load_config(workspace)
    model, base_url = resolve_llm_for_role(config, "scout")
    llm_client = LLMClient(
        provider_config={},
        mode="live",
        default_model=model,
        base_url=base_url,
    )

    agent = ScoutAgent(
        llm_client=llm_client,
        workspace_root=workspace,
    )

    for src in source:
        try:
            result, display_name = _ingest_one(
                agent, src, category, workspace, clip_web
            )
            if result.skipped:
                console.print(
                    f"[yellow]⊘[/yellow] Skipped "
                    f"[bold]{display_name}[/bold] (unchanged)"
                )
            elif result.success:
                console.print(
                    f"[green]✓[/green] Ingested "
                    f"[bold]{display_name}[/bold] → "
                    f"{result.manifest_key}"
                )
            else:
                console.print(f"[red]✗[/red] Failed: {result.message}")
                raise SystemExit(1)
        except SystemExit:
            raise
        except Exception as exc:
            console.print(f"[red]Error:[/red] {src}: {exc}")
            raise SystemExit(1) from exc


def _ingest_one(
    agent: object,
    source: str,
    category: str,
    workspace: Path,
    clip_web: object,
) -> tuple[object, str]:
    """Ingest a single source (file or URL). Returns (result, display_name)."""
    if _is_url(source):
        import hashlib

        assets_dir = workspace / "raw" / "assets"
        content, _assets = clip_web(source, assets_dir)  # type: ignore[operator]
        url_slug = hashlib.sha256(source.encode()).hexdigest()[:12]
        temp_file = workspace / "raw" / f"_web_{url_slug}.md"
        temp_file.write_text(content)
        try:
            result = agent.ingest(temp_file, category=category)  # type: ignore[union-attr]
        finally:
            temp_file.unlink(missing_ok=True)
        return result, source
    else:
        path = Path(source)
        if not path.exists():
            raise FileNotFoundError(f"File not found: {source}")
        result = agent.ingest(path.resolve(), category=category)  # type: ignore[union-attr]
        return result, str(path)
