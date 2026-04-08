"""Shared test helpers for Assistonauts tests.

FakeLLMClient, FakeResponse, and FakeEmbeddingClient are the single
source of truth for fake infrastructure in tests. Import from here
instead of defining local copies.
"""

from __future__ import annotations

import hashlib

from assistonauts.archivist.embeddings import EmbeddingClient


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


class FakeEmbeddingClient(EmbeddingClient):
    """Deterministic embedding client for testing.

    Generates reproducible embeddings from SHA-256 hashes of input text.
    Use this for unit tests where you need predictable vector outputs
    without a real embedding model.
    """

    def __init__(self, dimensions: int = 4) -> None:
        self._dimensions = dimensions

    @property
    def dimensions(self) -> int:
        return self._dimensions

    def embed(self, text: str) -> list[float]:
        h = hashlib.sha256(text.encode()).digest()
        return [b / 255.0 for b in h[: self._dimensions]]

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        return [self.embed(t) for t in texts]
