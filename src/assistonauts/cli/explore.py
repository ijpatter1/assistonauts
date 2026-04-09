"""CLI command: assistonauts explore — interactive Q&A against the knowledge base."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import click
from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel

from assistonauts.agents.explorer import ExplorerAgent
from assistonauts.archivist.service import Archivist

if TYPE_CHECKING:
    from assistonauts.agents.base import LLMClientProtocol
    from assistonauts.archivist.embeddings import EmbeddingClient

console = Console()

_REPL_COMMANDS = {
    "/quit": "Exit the Explorer session",
    "/save": "Save the last answer as an exploration",
    "/help": "Show available commands",
}


@click.command()
@click.option(
    "-w",
    "--workspace",
    default=".",
    type=click.Path(path_type=Path),
    help="Workspace root directory.",
)
@click.option(
    "--query",
    "-q",
    default=None,
    help="Ask a single question (non-interactive mode).",
)
@click.option(
    "--save",
    is_flag=True,
    default=False,
    help="Save the answer as an exploration (with --query).",
)
@click.option(
    "--max-tokens",
    default=8000,
    help="Maximum context tokens for article retrieval.",
)
def explore(
    workspace: Path,
    query: str | None,
    save: bool,
    max_tokens: int,
) -> None:
    """Launch an interactive Explorer session for Q&A against the knowledge base."""
    workspace = workspace.resolve()

    if not (workspace / ".assistonauts").exists():
        console.print(f"[red]Error:[/red] Workspace not found at {workspace}")
        raise SystemExit(1)

    # Initialize dependencies
    embedding_client = _create_embedding_client(workspace)
    llm_client = _create_llm_client(workspace)

    if embedding_client is None or llm_client is None:
        console.print(
            "[red]Error:[/red] Could not initialize LLM or embedding client. "
            "Check your workspace config."
        )
        raise SystemExit(1)

    from assistonauts.archivist.embeddings import get_embedding_dimensions
    from assistonauts.config.loader import load_config

    config = load_config(workspace)
    dims = get_embedding_dimensions(config.embedding)
    archivist = Archivist(workspace, embedding_dimensions=dims)

    explorer = ExplorerAgent(
        llm_client=llm_client,
        workspace_root=workspace,
        archivist=archivist,
        embedding_client=embedding_client,
        max_context_tokens=max_tokens,
    )

    if query:
        # Single-query mode
        _run_single_query(explorer, query, save=save)
    else:
        # Interactive REPL mode
        _run_repl(explorer)


def _run_single_query(
    explorer: ExplorerAgent,
    query: str,
    save: bool = False,
) -> None:
    """Execute a single query and display the result."""
    result = explorer.explore(query)
    _display_result(result)

    if save and result.success:
        path = explorer.file_exploration(result)
        console.print(f"\n[green]Saved[/green] exploration to {path}")


def _run_repl(explorer: ExplorerAgent) -> None:
    """Run the interactive REPL loop."""
    console.print(
        Panel(
            "Ask questions about your knowledge base.\n"
            "Type [bold]/help[/bold] for commands, "
            "[bold]/quit[/bold] to exit.",
            title="Explorer",
            border_style="blue",
        )
    )

    last_result = None

    while True:
        try:
            user_input = click.prompt(
                "", prompt_suffix="> ", default="", show_default=False
            )
        except (EOFError, click.Abort):
            break

        user_input = user_input.strip()
        if not user_input:
            continue

        # Handle commands
        if user_input == "/quit":
            break
        elif user_input == "/help":
            _show_help()
            continue
        elif user_input == "/save":
            if last_result and last_result.success:
                path = explorer.file_exploration(last_result)
                console.print(f"[green]Saved[/green] exploration to {path}")
            else:
                console.print("[yellow]No answer to save.[/yellow]")
            continue
        elif user_input.startswith("/"):
            console.print(f"[yellow]Unknown command:[/yellow] {user_input}")
            _show_help()
            continue

        # It's a question — explore it
        result = explorer.explore(user_input)
        _display_result(result)
        last_result = result


def _display_result(result: object) -> None:
    """Display an exploration result with Rich formatting."""
    from assistonauts.agents.explorer import ExplorerResult

    if not isinstance(result, ExplorerResult):
        return

    if not result.success:
        console.print(f"[red]Error:[/red] {result.answer}")
        return

    console.print()
    console.print(Markdown(result.formatted_answer))
    console.print()

    if result.citations:
        console.print(
            f"[dim]({result.articles_used} articles used, "
            f"{result.context_tokens_used} context tokens)[/dim]"
        )


def _show_help() -> None:
    """Display available REPL commands."""
    console.print("\n[bold]Commands:[/bold]")
    for cmd, desc in _REPL_COMMANDS.items():
        console.print(f"  [cyan]{cmd}[/cyan] — {desc}")
    console.print()


def _create_embedding_client(workspace: Path) -> EmbeddingClient | None:
    """Create an embedding client from workspace config."""
    from assistonauts.archivist.embeddings import create_embedding_client
    from assistonauts.config.loader import load_config

    try:
        config = load_config(workspace)
        return create_embedding_client(config.embedding)
    except Exception:
        return None


def _create_llm_client(workspace: Path) -> LLMClientProtocol | None:
    """Create an LLM client from workspace config."""
    from assistonauts.config.loader import load_config
    from assistonauts.llm.client import LLMClient

    try:
        config = load_config(workspace)
        llm_config = config.llm.get("default", {})
        model = llm_config.get("model", None) if isinstance(llm_config, dict) else None
        base_url = (
            llm_config.get("base_url", None) if isinstance(llm_config, dict) else None
        )
        return LLMClient(default_model=model, base_url=base_url)
    except Exception:
        return None
