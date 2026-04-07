"""Mission runner — executes single missions with audit trails and failure handling.

Runs one mission at a time, classifying failures as transient (retryable) or
deterministic (fail-fast). Writes YAML audit trail for each mission.
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import Enum
from pathlib import Path

import yaml

from assistonauts.agents.base import Agent, LLMClientProtocol


class MissionStatus(Enum):
    """Mission lifecycle states."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class TransientError(Exception):
    """Retryable error (API timeouts, rate limits, etc.)."""


class DeterministicError(Exception):
    """Non-retryable error (bad input, context overflow, etc.)."""


@dataclass
class Mission:
    """A single unit of agent work."""

    mission_id: str
    agent: str
    params: dict[str, str]
    status: MissionStatus = MissionStatus.PENDING


@dataclass
class MissionResult:
    """Result of executing a mission."""

    success: bool
    status: MissionStatus
    error_type: str = ""
    error_message: str = ""
    retry_count: int = 0
    agent_output: object = None


def _resolve_agent(
    agent_name: str,
    workspace_root: Path,
    llm_client: LLMClientProtocol,
) -> Agent:
    """Create an agent instance by name."""
    if agent_name == "compiler":
        from assistonauts.agents.compiler import CompilerAgent

        return CompilerAgent(llm_client=llm_client, workspace_root=workspace_root)
    elif agent_name == "scout":
        from assistonauts.agents.scout import ScoutAgent

        return ScoutAgent(llm_client=llm_client, workspace_root=workspace_root)
    else:
        raise DeterministicError(f"Unknown agent: {agent_name}")


class MissionRunner:
    """Executes single missions with YAML audit trail and failure classification.

    Transient errors (TransientError, ConnectionError, TimeoutError) are retried
    up to max_retries times. Deterministic errors fail immediately.
    """

    _TRANSIENT_EXCEPTIONS = (TransientError, ConnectionError, TimeoutError)

    def __init__(
        self,
        workspace_root: Path,
        missions_dir: Path,
        max_retries: int = 3,
        auto_commit: bool = False,
    ) -> None:
        self._workspace_root = workspace_root
        self._missions_dir = missions_dir
        self._max_retries = max_retries
        self._auto_commit = auto_commit

    def run(
        self,
        mission: Mission,
        llm_client: LLMClientProtocol,
    ) -> MissionResult:
        """Execute a mission, handling retries and writing audit trail."""
        mission.status = MissionStatus.RUNNING
        started_at = datetime.now(UTC).isoformat()
        retry_count = 0
        last_error = ""

        # Resolve agent
        try:
            agent = _resolve_agent(mission.agent, self._workspace_root, llm_client)
        except DeterministicError as e:
            mission.status = MissionStatus.FAILED
            result = MissionResult(
                success=False,
                status=MissionStatus.FAILED,
                error_type="deterministic",
                error_message=str(e),
            )
            self._write_audit(mission, started_at, result)
            return result

        # Execute with retry logic
        while True:
            try:
                agent_output = agent.run_mission(mission.params)
                mission.status = MissionStatus.COMPLETED
                result = MissionResult(
                    success=True,
                    status=MissionStatus.COMPLETED,
                    retry_count=retry_count,
                    agent_output=agent_output,
                )
                self._write_audit(mission, started_at, result)
                if self._auto_commit:
                    self._git_commit(mission)
                return result

            except self._TRANSIENT_EXCEPTIONS as e:
                retry_count += 1
                last_error = str(e)
                if retry_count > self._max_retries:
                    mission.status = MissionStatus.FAILED
                    result = MissionResult(
                        success=False,
                        status=MissionStatus.FAILED,
                        error_type="transient",
                        error_message=last_error,
                        retry_count=self._max_retries,
                    )
                    self._write_audit(mission, started_at, result)
                    return result
                # Retry — no backoff in v1 (simplicity over sophistication)
                continue

            except Exception as e:
                # All other errors are deterministic
                mission.status = MissionStatus.FAILED
                result = MissionResult(
                    success=False,
                    status=MissionStatus.FAILED,
                    error_type="deterministic",
                    error_message=str(e),
                    retry_count=retry_count,
                )
                self._write_audit(mission, started_at, result)
                return result

    def _write_audit(
        self,
        mission: Mission,
        started_at: str,
        result: MissionResult,
    ) -> None:
        """Write YAML audit trail for a mission."""
        self._missions_dir.mkdir(parents=True, exist_ok=True)
        audit_path = self._missions_dir / f"{mission.mission_id}.yaml"

        audit: dict[str, object] = {
            "mission_id": mission.mission_id,
            "agent": mission.agent,
            "params": mission.params,
            "status": mission.status.value,
            "started_at": started_at,
        }

        if result.success:
            audit["completed_at"] = datetime.now(UTC).isoformat()
        else:
            audit["failed_at"] = datetime.now(UTC).isoformat()
            audit["error_type"] = result.error_type
            audit["error_message"] = result.error_message

        if result.retry_count > 0:
            audit["retry_count"] = result.retry_count

        audit_path.write_text(yaml.dump(audit, default_flow_style=False))

    def _git_commit(self, mission: Mission) -> None:
        """Create a git commit for a completed mission."""
        try:
            subprocess.run(
                ["git", "add", "-A"],
                cwd=self._workspace_root,
                check=True,
                capture_output=True,
            )
            title = mission.params.get("title", "article")
            msg = f"[mission-{mission.mission_id}] {mission.agent}: process {title}"
            subprocess.run(
                ["git", "commit", "-m", msg],
                cwd=self._workspace_root,
                check=True,
                capture_output=True,
            )
        except subprocess.CalledProcessError:
            # Non-critical — log but don't fail the mission
            pass
