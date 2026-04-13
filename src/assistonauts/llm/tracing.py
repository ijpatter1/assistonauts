"""LLM call tracing — thread-local context for caller metadata.

The trace_context thread-local allows agents and the orchestrator to
attach metadata (agent role, mission ID, iteration phase) that the
LLMClient includes in its on_llm_call callback records. This decouples
the LLM client from orchestration concerns while enabling end-to-end
tracing of every non-deterministic operation.
"""

from __future__ import annotations

import threading

_trace_context = threading.local()


def set_trace_context(**kwargs: str) -> None:
    """Set trace context values for the current thread.

    These values are included in the on_llm_call callback record
    under the 'context' key. Call clear_trace_context() when done.

    Example:
        set_trace_context(agent="captain", mission_id="m-001", phase="structuring")
    """
    if not hasattr(_trace_context, "data"):
        _trace_context.data = {}
    _trace_context.data.update(kwargs)


def clear_trace_context() -> None:
    """Remove all trace context values for the current thread."""
    _trace_context.data = {}


def get_trace_context() -> dict[str, str]:
    """Get a copy of the current trace context."""
    if not hasattr(_trace_context, "data"):
        return {}
    return dict(_trace_context.data)
