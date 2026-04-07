"""Shared test fixtures for Assistonauts."""

from pathlib import Path

import pytest


@pytest.fixture
def tmp_workspace(tmp_path: Path) -> Path:
    """Provide a temporary directory to use as a workspace root."""
    return tmp_path
