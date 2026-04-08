"""Shared test fixtures for Assistonauts."""

from __future__ import annotations

from pathlib import Path

import pytest

from assistonauts.llm.client import LLMClient
from tests.helpers import FakeLLMClient


@pytest.fixture
def tmp_workspace(tmp_path: Path) -> Path:
    """Provide a temporary directory to use as a workspace root."""
    return tmp_path


@pytest.fixture
def fake_llm_client() -> FakeLLMClient:
    """Provide a fake LLM client that returns 'default response'."""
    return FakeLLMClient()


@pytest.fixture
def replay_llm_client(tmp_path: Path) -> LLMClient:
    """Provide an LLM client in replay mode pointed at tests/fixtures/."""
    fixture_dir = Path(__file__).parent / "fixtures" / "scout"
    if not fixture_dir.exists():
        fixture_dir = tmp_path / "fixtures"
        fixture_dir.mkdir()
    return LLMClient(
        provider_config={},
        mode="replay",
        fixture_dir=fixture_dir,
    )


@pytest.fixture
def initialized_workspace(tmp_path: Path) -> Path:
    """Provide a fully initialized workspace for integration-style tests."""
    from assistonauts.storage.workspace import init_workspace

    return init_workspace(tmp_path)
