"""Shared test fixtures for Assistonauts."""

import os
import tempfile
from pathlib import Path

import pytest


@pytest.fixture
def tmp_workspace(tmp_path: Path) -> Path:
    """Provide a temporary directory to use as a workspace root."""
    return tmp_path


@pytest.fixture
def clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Ensure tests don't leak environment variables."""
    monkeypatch.delenv("ASSISTONAUTS_CONFIG", raising=False)
