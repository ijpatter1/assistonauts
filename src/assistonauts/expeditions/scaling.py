"""Deterministic scaling system for agent instances.

Config-driven, no LLM calls. Enforces singleton rules for Captain,
Curator, and Inspector. Manages instance pools for scalable agents
(Scout, Compiler, Explorer).
"""

from __future__ import annotations

import re
import uuid

from assistonauts.models.config import SINGLETONS, ScalingConfig


class AgentPool:
    """Manages instances for a single agent type."""

    def __init__(self, agent_type: str, max_instances: int) -> None:
        self.agent_type = agent_type
        self.max_instances = max_instances
        self._active: set[str] = set()

    def acquire(self) -> str | None:
        """Acquire an instance slot. Returns instance_id or None."""
        if len(self._active) >= self.max_instances:
            return None
        instance_id = f"{self.agent_type}-{uuid.uuid4().hex[:8]}"
        self._active.add(instance_id)
        return instance_id

    def release(self, instance_id: str) -> None:
        """Release an instance slot."""
        self._active.discard(instance_id)

    def active_count(self) -> int:
        return len(self._active)


class ScalingManager:
    """Deterministic agent scaling based on config rules.

    No LLM calls. Pure config-driven decisions.
    """

    def __init__(self, config: ScalingConfig) -> None:
        self.config = config
        self._pools: dict[str, AgentPool] = {}

    def _get_pool(self, agent_type: str) -> AgentPool:
        if agent_type not in self._pools:
            if agent_type in SINGLETONS or agent_type not in self.config.agents:
                max_inst = 1
            else:
                max_inst = self.config.auto_scale.max_instances
            self._pools[agent_type] = AgentPool(agent_type, max_inst)
        return self._pools[agent_type]

    def acquire(self, agent_type: str) -> str | None:
        """Acquire an agent instance. Returns instance_id or None."""
        return self._get_pool(agent_type).acquire()

    def release(self, agent_type: str, instance_id: str) -> None:
        """Release an agent instance."""
        self._get_pool(agent_type).release(instance_id)

    def should_scale_up(
        self,
        agent_type: str,
        queue_depth: int,
    ) -> bool:
        """Check if auto-scaling should trigger for this agent."""
        if agent_type in SINGLETONS:
            return False
        if agent_type not in self.config.agents:
            return False

        trigger = self.config.auto_scale.trigger
        threshold = _parse_trigger(trigger)
        pool = self._get_pool(agent_type)
        return queue_depth > threshold and pool.active_count() < pool.max_instances

    def active_counts(self) -> dict[str, int]:
        """Return active instance counts per agent type."""
        return {
            agent_type: pool.active_count()
            for agent_type, pool in self._pools.items()
            if pool.active_count() > 0
        }


def _parse_trigger(trigger: str) -> int:
    """Parse a trigger expression like 'queue_depth > 5'."""
    match = re.search(r">\s*(\d+)", trigger)
    if match:
        return int(match.group(1))
    return 5  # default
