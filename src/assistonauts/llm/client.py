"""Provider-agnostic LLM client with record/replay for testing."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class LLMResponse:
    """Response from an LLM completion call."""

    content: str
    model: str
    usage: dict[str, int] = field(default_factory=dict)


def _call_litellm(
    messages: list[dict[str, str]],
    model: str | None = None,
    system: str | None = None,
    **kwargs: object,
) -> LLMResponse:
    """Call litellm.completion and wrap the response.

    Separated as a module-level function for easy mocking in tests.
    """
    import litellm

    litellm_messages: list[dict[str, str]] = []
    if system:
        litellm_messages.append({"role": "system", "content": system})
    litellm_messages.extend(messages)

    response = litellm.completion(
        model=model or "gpt-3.5-turbo",
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
    ) -> None:
        if mode not in _VALID_MODES:
            raise ValueError(f"Invalid mode '{mode}'. Must be one of: {_VALID_MODES}")
        if mode in ("record", "replay") and fixture_dir is None:
            raise ValueError(f"fixture_dir is required for mode '{mode}'")

        self._provider_config = provider_config
        self._mode = mode
        self._fixture_dir = fixture_dir

    @property
    def mode(self) -> str:
        return self._mode

    def complete(
        self,
        messages: list[dict[str, str]],
        model: str | None = None,
        system: str | None = None,
        **kwargs: object,
    ) -> LLMResponse:
        """Make an inference call. Behavior depends on mode."""
        if self._mode == "replay":
            return self._replay(messages, system=system)
        elif self._mode == "record":
            response = _call_litellm(messages, model=model, system=system, **kwargs)
            self._save_fixture(messages, system=system, response=response)
            return response
        else:  # live
            return _call_litellm(messages, model=model, system=system, **kwargs)

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
