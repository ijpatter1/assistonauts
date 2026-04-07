"""Shared test fixtures for Assistonauts."""

from __future__ import annotations

from pathlib import Path

import pytest

from assistonauts.llm.client import LLMClient


class FakeResponse:
    """Minimal fake LLM response for testing."""

    def __init__(self, content: str) -> None:
        self.content = content
        self.model = "fake-model"
        self.usage = {"prompt_tokens": 10, "completion_tokens": 5}


class FakeLLMClient:
    """Fake LLM client that returns canned responses.

    Use this for unit tests where you need predictable LLM responses
    without the replay fixture infrastructure.
    """

    def __init__(self, responses: list[str] | None = None) -> None:
        self._responses = list(responses or ["default response"])
        self._call_count = 0
        self.calls: list[dict[str, object]] = []

    def complete(
        self,
        messages: list[dict[str, str]],
        model: str | None = None,
        system: str | None = None,
        **kwargs: object,
    ) -> FakeResponse:
        self.calls.append({"messages": messages, "model": model, "system": system})
        idx = min(self._call_count, len(self._responses) - 1)
        self._call_count += 1
        return FakeResponse(self._responses[idx])


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
