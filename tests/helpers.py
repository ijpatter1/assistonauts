"""Shared test helpers for Assistonauts tests.

FakeLLMClient and FakeResponse are the single source of truth for
fake LLM infrastructure in tests. Import from here instead of
defining local copies.
"""

from __future__ import annotations


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
