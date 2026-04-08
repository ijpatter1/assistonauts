"""Shared toolkit — logger, config reader, cache interface, file I/O.

These functions are shared across all agents. Agent-specific toolkit
functions live in their own modules (e.g., tools/scout.py).
"""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from pathlib import Path


class StructuredLogger:
    """Structured logger that writes JSON-lines to task log files.

    Each log entry includes timestamp, agent role, event type, and
    context-specific data (token counts, file paths, tool names, etc.).
    Also logs to Python's standard logging for console output.
    """

    def __init__(
        self,
        role: str,
        log_dir: Path | None = None,
        task_id: str | None = None,
    ) -> None:
        self._role = role
        self._log_dir = log_dir
        self._task_id = task_id
        self._logger = logging.getLogger(f"assistonauts.{role}")
        self._log_file: Path | None = None

        if log_dir is not None:
            log_dir.mkdir(parents=True, exist_ok=True)
            filename = f"{role}"
            if task_id:
                filename += f"_{task_id}"
            filename += ".jsonl"
            self._log_file = log_dir / filename

    def log(
        self,
        event: str,
        **data: object,
    ) -> None:
        """Write a structured log entry.

        Args:
            event: Event type (e.g., "llm_call", "tool_invoke", "file_write")
            **data: Additional context (token_count, path, tool_name, etc.)
        """
        entry = {
            "timestamp": datetime.now(UTC).isoformat(),
            "role": self._role,
            "event": event,
            **data,
        }
        if self._task_id:
            entry["task_id"] = self._task_id

        # Log to Python logger
        self._logger.info("%s: %s", event, json.dumps(data, default=str))

        # Append to log file if configured
        if self._log_file is not None:
            with open(self._log_file, "a") as f:
                f.write(json.dumps(entry, default=str) + "\n")

    def log_llm_call(
        self,
        model: str,
        prompt_tokens: int,
        completion_tokens: int,
        **extra: object,
    ) -> None:
        """Log an LLM inference call with token counts."""
        self.log(
            "llm_call",
            model=model,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            **extra,
        )

    def log_tool_invoke(self, tool_name: str, **extra: object) -> None:
        """Log a toolkit function invocation."""
        self.log("tool_invoke", tool_name=tool_name, **extra)

    def log_file_write(self, path: str, **extra: object) -> None:
        """Log a file write operation."""
        self.log("file_write", path=path, **extra)
