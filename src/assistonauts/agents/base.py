"""Base agent class for all Assistonauts agents."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

from assistonauts.tools.shared import StructuredLogger


class OwnershipError(PermissionError):
    """Raised when an agent tries to access a path outside its boundaries."""

    def __init__(self, role: str, path: Path, allowed: list[Path]) -> None:
        allowed_str = ", ".join(str(d) for d in allowed)
        super().__init__(
            f"Agent '{role}' cannot access {path}. Allowed directories: [{allowed_str}]"
        )
        self.role = role
        self.path = path
        self.allowed = allowed


class LLMResponse(Protocol):
    """Protocol for LLM response objects."""

    @property
    def content(self) -> str: ...


class LLMClientProtocol(Protocol):
    """Protocol for injectable LLM clients."""

    def complete(
        self,
        messages: list[dict[str, str]],
        model: str | None = None,
        system: str | None = None,
        **kwargs: object,
    ) -> LLMResponse: ...


@dataclass
class Agent:
    """Base class for all Assistonauts agents.

    Provides ownership-enforced file I/O, toolkit registration,
    and LLM client integration. Subclasses implement run_mission().
    """

    role: str
    system_prompt: str
    llm_client: LLMClientProtocol
    owned_dirs: list[Path]
    readable_dirs: list[Path]
    toolkit: dict[str, Callable[..., object]] = field(default_factory=dict)
    logger: StructuredLogger | None = None

    def __post_init__(self) -> None:
        """Create a default logger if none was provided."""
        if self.logger is None:
            self.logger = StructuredLogger(role=self.role)

    def run_mission(self, mission: object) -> object:
        """Execute a mission. Subclasses must override."""
        raise NotImplementedError(f"Agent '{self.role}' must implement run_mission()")

    def read_file(self, path: Path) -> str:
        """Read a file, enforcing readable_dirs + owned_dirs boundary."""
        resolved = path.resolve()
        allowed = self.owned_dirs + self.readable_dirs
        if not self._is_within(resolved, allowed):
            raise OwnershipError(self.role, path, allowed)
        return resolved.read_text()

    def write_file(self, path: Path, content: str) -> None:
        """Write a file, enforcing owned_dirs boundary."""
        resolved = path.resolve()
        if not self._is_within(resolved, self.owned_dirs):
            raise OwnershipError(self.role, path, self.owned_dirs)
        resolved.parent.mkdir(parents=True, exist_ok=True)
        resolved.write_text(content)
        assert self.logger is not None
        self.logger.log_file_write(str(resolved))

    def call_llm(self, messages: list[dict[str, str]], **kwargs: object) -> str:
        """Call LLM via the injected client with this agent's system prompt."""
        response = self.llm_client.complete(
            messages=messages,
            system=self.system_prompt,
            **kwargs,
        )
        assert self.logger is not None
        usage = getattr(response, "usage", {})
        p_tokens = usage.get("prompt_tokens", 0) if isinstance(usage, dict) else 0
        c_tokens = usage.get("completion_tokens", 0) if isinstance(usage, dict) else 0
        self.logger.log_llm_call(
            model=getattr(response, "model", "unknown"),
            prompt_tokens=p_tokens,
            completion_tokens=c_tokens,
        )
        return response.content

    @staticmethod
    def _is_within(path: Path, allowed_dirs: list[Path]) -> bool:
        """Check if path is within any of the allowed directories."""
        resolved = path.resolve()
        for allowed in allowed_dirs:
            try:
                resolved.relative_to(allowed.resolve())
                return True
            except ValueError:
                continue
        return False
