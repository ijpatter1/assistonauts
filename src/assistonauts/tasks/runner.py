"""Task runner — executes single tasks with audit trails and failure handling.

Runs one task at a time, classifying failures as transient (retryable) or
deterministic (fail-fast). Writes YAML audit trail for each task.
"""

from __future__ import annotations

import logging
import subprocess
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import Enum
from pathlib import Path

import yaml

from assistonauts.agents.base import Agent, AgentResult, LLMClientProtocol

logger = logging.getLogger("assistonauts.tasks")


class TaskStatus(Enum):
    """Task lifecycle states."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class TransientError(Exception):
    """Retryable error (API timeouts, rate limits, etc.)."""


class DeterministicError(Exception):
    """Non-retryable error (bad input, context overflow, etc.)."""


@dataclass
class Task:
    """A single unit of agent work."""

    task_id: str
    agent: str
    params: dict[str, str]
    status: TaskStatus = TaskStatus.PENDING


@dataclass
class TaskResult:
    """Result of executing a task."""

    success: bool
    status: TaskStatus
    error_type: str = ""
    error_message: str = ""
    retry_count: int = 0
    agent_output: AgentResult | None = None


def _resolve_agent(
    agent_name: str,
    workspace_root: Path,
    llm_client: LLMClientProtocol,
    agent_context: dict[str, object] | None = None,
) -> Agent:
    """Create an agent instance by name.

    agent_context provides optional dependencies (archivist, embedding_client)
    that certain agents require. When not provided, agents that need them
    will fail gracefully via their own validation.
    """
    ctx = agent_context or {}
    if agent_name == "compiler":
        from assistonauts.agents.compiler import CompilerAgent

        return CompilerAgent(
            llm_client=llm_client,
            workspace_root=workspace_root,
            expedition_scope=str(ctx.get("expedition_scope", "")),
            expedition_purpose=str(ctx.get("expedition_purpose", "")),
        )
    elif agent_name == "scout":
        from assistonauts.agents.scout import ScoutAgent

        return ScoutAgent(llm_client=llm_client, workspace_root=workspace_root)
    elif agent_name == "captain":
        from assistonauts.agents.captain import CaptainAgent

        return CaptainAgent(llm_client=llm_client, workspace_root=workspace_root)
    elif agent_name == "curator":
        from assistonauts.agents.curator import CuratorAgent

        return CuratorAgent(
            llm_client=llm_client,
            workspace_root=workspace_root,
            archivist=ctx.get("archivist"),  # type: ignore[arg-type]
            embedding_client=ctx.get("embedding_client"),  # type: ignore[arg-type]
        )
    elif agent_name == "explorer":
        from assistonauts.agents.explorer import ExplorerAgent

        return ExplorerAgent(
            llm_client=llm_client,
            workspace_root=workspace_root,
            archivist=ctx.get("archivist"),  # type: ignore[arg-type]
            embedding_client=ctx.get("embedding_client"),  # type: ignore[arg-type]
        )
    else:
        raise DeterministicError(f"Unknown agent: {agent_name}")


class TaskRunner:
    """Executes single tasks with YAML audit trail and failure classification.

    Transient errors (TransientError, ConnectionError, TimeoutError) are retried
    up to max_retries times. Deterministic errors fail immediately.
    """

    _TRANSIENT_EXCEPTIONS = (TransientError, ConnectionError, TimeoutError)

    def __init__(
        self,
        workspace_root: Path,
        tasks_dir: Path,
        max_retries: int = 3,
        auto_commit: bool = False,
        agent_context: dict[str, object] | None = None,
    ) -> None:
        self._workspace_root = workspace_root
        self._tasks_dir = tasks_dir
        self._max_retries = max_retries
        self._auto_commit = auto_commit
        self._agent_context = agent_context or {}

    def run(
        self,
        task: Task,
        llm_client: LLMClientProtocol,
    ) -> TaskResult:
        """Execute a task, handling retries and writing audit trail."""
        task.status = TaskStatus.RUNNING
        started_at = datetime.now(UTC).isoformat()
        retry_count = 0
        last_error = ""

        # Resolve agent
        try:
            agent = _resolve_agent(
                task.agent, self._workspace_root, llm_client, self._agent_context
            )
        except DeterministicError as e:
            task.status = TaskStatus.FAILED
            result = TaskResult(
                success=False,
                status=TaskStatus.FAILED,
                error_type="deterministic",
                error_message=str(e),
            )
            self._write_audit(task, started_at, result)
            return result

        # Execute with retry logic. The finally block releases agent
        # resources — critical for singleton agents like Curator.
        try:
            while True:
                try:
                    agent_output = agent.run_task(task.params)
                    # Check agent-level success (e.g. CuratorResult.success)
                    if hasattr(agent_output, "success") and not agent_output.success:
                        task.status = TaskStatus.FAILED
                        msg = getattr(agent_output, "message", "Agent reported failure")
                        result = TaskResult(
                            success=False,
                            status=TaskStatus.FAILED,
                            error_type="deterministic",
                            error_message=str(msg),
                            retry_count=retry_count,
                            agent_output=agent_output,
                        )
                        self._write_audit(task, started_at, result)
                        return result
                    task.status = TaskStatus.COMPLETED
                    result = TaskResult(
                        success=True,
                        status=TaskStatus.COMPLETED,
                        retry_count=retry_count,
                        agent_output=agent_output,
                    )
                    self._write_audit(task, started_at, result)
                    if self._auto_commit:
                        self._git_commit(task, agent_output)
                    return result

                except self._TRANSIENT_EXCEPTIONS as e:
                    retry_count += 1
                    last_error = str(e)
                    if retry_count > self._max_retries:
                        task.status = TaskStatus.FAILED
                        result = TaskResult(
                            success=False,
                            status=TaskStatus.FAILED,
                            error_type="transient",
                            error_message=last_error,
                            retry_count=self._max_retries,
                        )
                        self._write_audit(task, started_at, result)
                        return result
                    continue

                except Exception as e:
                    task.status = TaskStatus.FAILED
                    result = TaskResult(
                        success=False,
                        status=TaskStatus.FAILED,
                        error_type="deterministic",
                        error_message=str(e),
                        retry_count=retry_count,
                    )
                    self._write_audit(task, started_at, result)
                    return result
        finally:
            if hasattr(agent, "close"):
                agent.close()

    def _relativize_params(self, params: dict[str, str]) -> dict[str, str]:
        """Convert absolute paths in task params to workspace-relative paths."""
        result: dict[str, str] = {}
        for key, value in params.items():
            if key in ("source_path", "source_paths"):
                # Handle comma-separated paths for source_paths
                parts = value.split(",") if key == "source_paths" else [value]
                relativized: list[str] = []
                for part in parts:
                    p = part.strip()
                    try:
                        rel = str(Path(p).relative_to(self._workspace_root))
                        relativized.append(rel)
                    except ValueError:
                        relativized.append(p)
                if key == "source_paths":
                    result[key] = ", ".join(relativized)
                else:
                    result[key] = relativized[0]
            else:
                result[key] = value
        return result

    def _write_audit(
        self,
        task: Task,
        started_at: str,
        result: TaskResult,
    ) -> None:
        """Write YAML audit trail for a task."""
        self._tasks_dir.mkdir(parents=True, exist_ok=True)
        audit_path = self._tasks_dir / f"{task.task_id}.yaml"

        audit: dict[str, object] = {
            "task_id": task.task_id,
            "agent": task.agent,
            "params": self._relativize_params(task.params),
            "status": task.status.value,
            "started_at": started_at,
        }

        if result.success:
            audit["completed_at"] = datetime.now(UTC).isoformat()
            # Record output details for traceability
            if result.agent_output:
                output = result.agent_output
                if output.output_path:
                    try:
                        rel = str(output.output_path.relative_to(self._workspace_root))
                    except ValueError:
                        rel = str(output.output_path)
                    audit["output_path"] = rel
                if output.output_paths:
                    rel_paths = []
                    for p in output.output_paths:
                        try:
                            rel_paths.append(str(p.relative_to(self._workspace_root)))
                        except ValueError:
                            rel_paths.append(str(p))
                    audit["output_paths"] = rel_paths
        else:
            audit["failed_at"] = datetime.now(UTC).isoformat()
            audit["error_type"] = result.error_type
            audit["error_message"] = result.error_message

        if result.retry_count > 0:
            audit["retry_count"] = result.retry_count

        audit_path.write_text(yaml.dump(audit, default_flow_style=False))

    def _git_commit(self, task: Task, agent_output: AgentResult) -> None:
        """Create a git commit for a completed task.

        Stages only the files produced by the agent (via agent_output.output_paths)
        plus the task audit trail, rather than blindly staging all workspace changes.
        """
        # Collect files to stage: agent outputs + audit trail
        paths_to_stage: list[str] = []
        for p in agent_output.output_paths:
            paths_to_stage.append(str(p))
        audit_path = self._tasks_dir / f"{task.task_id}.yaml"
        if audit_path.exists():
            paths_to_stage.append(str(audit_path))
        # Also stage the manifest (updated by the agent)
        manifest_path = self._workspace_root / "index" / "manifest.json"
        if manifest_path.exists():
            paths_to_stage.append(str(manifest_path))

        try:
            subprocess.run(
                ["git", "add", "--", *paths_to_stage],
                cwd=self._workspace_root,
                check=True,
                capture_output=True,
            )
            title = task.params.get("title", "article")
            msg = f"[task-{task.task_id}] {task.agent}: process {title}"
            subprocess.run(
                ["git", "commit", "-m", msg],
                cwd=self._workspace_root,
                check=True,
                capture_output=True,
            )
        except subprocess.CalledProcessError as exc:
            logger.warning(
                "Git commit failed for task %s: %s",
                task.task_id,
                exc.stderr.decode() if exc.stderr else str(exc),
            )
