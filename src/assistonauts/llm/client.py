"""Provider-agnostic LLM client with record/replay for testing."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from assistonauts.cache.llm_cache import LLMResponseCache
from assistonauts.llm.tracing import get_trace_context


@dataclass
class LLMResponse:
    """Response from an LLM completion call."""

    content: str
    model: str
    usage: dict[str, int] = field(default_factory=dict)


def _call_litellm(
    messages: list[dict[str, object]],
    model: str | None = None,
    system: str | None = None,
    **kwargs: object,
) -> LLMResponse:
    """Call litellm.completion and wrap the response.

    Separated as a module-level function for easy mocking in tests.
    Messages can contain multimodal content blocks (image_url, etc.)
    for vision model calls.
    """
    import litellm

    litellm_messages: list[dict[str, object]] = []
    if system:
        litellm_messages.append({"role": "system", "content": system})
    litellm_messages.extend(messages)

    response = litellm.completion(
        model=model or "ollama/gemma4:e2b",  # fallback for direct calls
        messages=litellm_messages,
        **kwargs,
    )

    # litellm.completion() returns ModelResponse | CustomStreamWrapper.
    # We never stream, so it's always ModelResponse — but the type union
    # prevents mypy from narrowing .choices, .model, .usage attributes.
    choice = response.choices[0]  # type: ignore[union-attr]
    return LLMResponse(
        content=choice.message.content,  # type: ignore[union-attr]
        model=response.model or model or "",  # type: ignore[union-attr]
        usage=dict(response.usage) if response.usage else {},  # type: ignore[union-attr]
    )


_VALID_MODES = {"live", "record", "replay"}


class LLMClient:
    """Provider-agnostic LLM wrapper with record/replay for testing.

    Modes:
        - live: calls litellm, no caching
        - record: calls litellm, saves request/response to fixture_dir
        - replay: returns saved responses from fixture_dir, no API calls
    """

    def __init__(
        self,
        provider_config: dict[str, object],
        mode: str = "live",
        fixture_dir: Path | None = None,
        default_model: str = "ollama/gemma4:e2b",
        base_url: str | None = None,
        cache_path: Path | None = None,
        on_llm_call: Callable[[dict[str, object]], None] | None = None,
    ) -> None:
        if mode not in _VALID_MODES:
            raise ValueError(f"Invalid mode '{mode}'. Must be one of: {_VALID_MODES}")
        if mode in ("record", "replay") and fixture_dir is None:
            raise ValueError(f"fixture_dir is required for mode '{mode}'")

        self._provider_config = provider_config
        self._mode = mode
        self._fixture_dir = fixture_dir
        self._default_model = default_model
        self._base_url = base_url
        self._cache: LLMResponseCache | None = (
            LLMResponseCache(cache_path) if cache_path else None
        )
        self._on_llm_call = on_llm_call
        self.total_tokens_used: int = 0

    @property
    def mode(self) -> str:
        return self._mode

    @property
    def default_model(self) -> str:
        return self._default_model

    @property
    def base_url(self) -> str | None:
        return self._base_url

    def complete(
        self,
        messages: list[dict[str, object]],
        model: str | None = None,
        system: str | None = None,
        **kwargs: object,
    ) -> LLMResponse:
        """Make an inference call. Behavior depends on mode.

        When a cache_path was provided at init, the cache is checked
        before making API calls (in live/record modes) and responses
        are stored after successful calls.

        If on_llm_call was provided, fires the callback with the full
        request/response data on every call, regardless of mode or
        cache status.
        """
        resolved_model = model or self._default_model
        if self._base_url and "base_url" not in kwargs:
            kwargs["base_url"] = self._base_url

        response: LLMResponse | None = None

        if self._mode == "replay":
            response = self._replay(messages, system=system)
        elif self._cache is not None:
            # Check cache before making API call (live and record modes)
            cached = self._cache.get(resolved_model, system, messages)
            if cached is not None:
                usage = cached["usage"] if isinstance(cached["usage"], dict) else {}
                response = LLMResponse(
                    content=str(cached["content"]),
                    model=resolved_model,
                    usage=usage,
                )

        if response is None:
            if self._mode == "record":
                response = _call_litellm(
                    messages, model=resolved_model, system=system, **kwargs
                )
                self._save_fixture(messages, system=system, response=response)
            else:  # live
                response = _call_litellm(
                    messages, model=resolved_model, system=system, **kwargs
                )

            # Store in cache after successful API call
            if self._cache is not None:
                self._cache.put(
                    model=resolved_model,
                    system=system,
                    messages=messages,
                    content=response.content,
                    usage=response.usage,
                )

        self._track_tokens(response.usage)
        self._fire_callback(messages, system, response)
        return response

    def _fire_callback(
        self,
        messages: list[dict[str, object]],
        system: str | None,
        response: LLMResponse,
    ) -> None:
        """Fire the on_llm_call callback if configured."""
        if self._on_llm_call is None:
            return
        record: dict[str, object] = {
            "timestamp": datetime.now(UTC).isoformat(),
            "messages": messages,
            "system": system,
            "model": response.model,
            "response": response.content,
            "usage": response.usage,
            "context": get_trace_context(),
        }
        self._on_llm_call(record)

    def _track_tokens(self, usage: dict[str, int]) -> None:
        """Accumulate token usage from any response path."""
        if isinstance(usage, dict):
            self.total_tokens_used += usage.get("prompt_tokens", 0) + usage.get(
                "completion_tokens", 0
            )

    def _replay(
        self,
        messages: list[dict[str, str]],
        system: str | None = None,
    ) -> LLMResponse:
        """Load a response from a saved fixture."""
        key = self._fixture_key(messages, system=system)
        assert self._fixture_dir is not None
        fixture_path = self._fixture_dir / f"{key}.json"

        if not fixture_path.exists():
            raise FileNotFoundError(
                f"No fixture found for key '{key}'. Expected file: {fixture_path}"
            )

        data = json.loads(fixture_path.read_text())
        return LLMResponse(
            content=data["content"],
            model=data.get("model", ""),
            usage=data.get("usage", {}),
        )

    def _save_fixture(
        self,
        messages: list[dict[str, str]],
        system: str | None,
        response: LLMResponse,
    ) -> None:
        """Save a response as a fixture file."""
        key = self._fixture_key(messages, system=system)
        assert self._fixture_dir is not None
        fixture_path = self._fixture_dir / f"{key}.json"

        data = {
            "content": response.content,
            "model": response.model,
            "usage": response.usage,
        }
        fixture_path.write_text(json.dumps(data, indent=2))

    def _fixture_key(
        self,
        messages: list[dict[str, str]],
        system: str | None = None,
    ) -> str:
        """Generate a deterministic key for fixture lookup.

        SHA-256 of (system + messages) serialized as JSON.
        """
        payload = json.dumps(
            {"system": system, "messages": messages},
            sort_keys=True,
        )
        return hashlib.sha256(payload.encode()).hexdigest()[:16]
