"""Assistonauts CLI entry point."""

import click


@click.group()
@click.version_option(package_name="assistonauts")
def cli() -> None:
    """Assistonauts — LLM-powered knowledge base framework."""
