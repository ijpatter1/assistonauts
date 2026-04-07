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
@click.argument("source")
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
def ingest(source: str, category: str, workspace: Path) -> None:
    """Ingest a source file or URL into the knowledge base."""
    from assistonauts.agents.scout import ScoutAgent
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

    # Create a minimal LLM client (Scout mostly uses toolkit, not LLM)
    llm_client = LLMClient(provider_config={}, mode="live")

    agent = ScoutAgent(
        llm_client=llm_client,
        workspace_root=workspace,
    )

    try:
        if _is_url(source):
            # Web clipping: download URL to temp, then ingest
            assets_dir = workspace / "raw" / "assets"
            content, _assets = clip_web(source, assets_dir)

            # Write clipped content to a temp file for ingestion
            import hashlib

            url_slug = hashlib.sha256(source.encode()).hexdigest()[:12]
            temp_file = workspace / "raw" / f"_web_{url_slug}.md"
            temp_file.write_text(content)
            try:
                result = agent.ingest(temp_file, category=category)
            finally:
                temp_file.unlink(missing_ok=True)

            display_name = source
        else:
            path = Path(source)
            if not path.exists():
                console.print(f"[red]Error:[/red] File not found: {source}")
                raise SystemExit(1)
            result = agent.ingest(path.resolve(), category=category)
            display_name = str(path)

        if result.skipped:
            console.print(
                f"[yellow]⊘[/yellow] Skipped [bold]{display_name}[/bold] (unchanged)"
            )
        elif result.success:
            key = result.manifest_key
            console.print(
                f"[green]✓[/green] Ingested [bold]{display_name}[/bold] → {key}"
            )
        else:
            console.print(f"[red]✗[/red] Failed: {result.message}")
            raise SystemExit(1)
    except SystemExit:
        raise
    except Exception as exc:
        console.print(f"[red]Error:[/red] {exc}")
        raise SystemExit(1) from exc
