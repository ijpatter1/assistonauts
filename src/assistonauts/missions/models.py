"""Mission model and state machine for multi-step objectives."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum

from assistonauts.tasks.runner import TaskStatus


class MissionStatus(Enum):
    """Mission lifecycle states."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    STALE = "stale"


@dataclass
class FailureRecord:
    """Records details of a mission failure."""

    error_type: str  # "transient" or "deterministic"
    error_message: str
    retries: int = 0
    failed_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    @property
    def is_deterministic(self) -> bool:
        return self.error_type == "deterministic"


@dataclass
class MissionTask:
    """Reference to a task within a mission's ordered sequence."""

    task_id: str
    agent: str
    params: dict[str, str]
    order: int
    status: TaskStatus = TaskStatus.PENDING


@dataclass
class Mission:
    """A scoped objective that decomposes into ordered task sequences.

    Missions are created by the Captain. Each mission targets a specific agent
    and contains acceptance criteria that define completion. Tasks within the
    mission are executed sequentially via the Phase 2 TaskRunner.
    """

    mission_id: str
    agent: str
    mission_type: str
    inputs: dict[str, list[str] | str]
    acceptance_criteria: list[str]
    created_by: str
    status: MissionStatus = MissionStatus.PENDING
    priority: str = "normal"
    checklist: list[str] = field(default_factory=list)
    tasks: list[MissionTask] = field(default_factory=list)
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    started_at: datetime | None = None
    completed_at: datetime | None = None
    failure: FailureRecord | None = None

    # --- State transitions ---

    def start(self) -> None:
        if self.status != MissionStatus.PENDING:
            msg = f"Cannot start mission in state {self.status.value}"
            raise ValueError(msg)
        self.status = MissionStatus.RUNNING
        self.started_at = datetime.now(UTC)

    def complete(self) -> None:
        if self.status != MissionStatus.RUNNING:
            msg = f"Cannot complete mission in state {self.status.value}"
            raise ValueError(msg)
        self.status = MissionStatus.COMPLETED
        self.completed_at = datetime.now(UTC)

    def fail(
        self,
        error_type: str,
        error_message: str,
        retries: int = 0,
    ) -> None:
        if self.status != MissionStatus.RUNNING:
            msg = f"Cannot fail mission in state {self.status.value}"
            raise ValueError(msg)
        self.status = MissionStatus.FAILED
        self.failure = FailureRecord(
            error_type=error_type,
            error_message=error_message,
            retries=retries,
        )

    def mark_stale(self, reason: str) -> None:
        if self.status != MissionStatus.COMPLETED:
            msg = f"Cannot mark stale mission in state {self.status.value}"
            raise ValueError(msg)
        self.status = MissionStatus.STALE

    def retry(self) -> None:
        if self.status != MissionStatus.FAILED:
            msg = f"Cannot retry mission in state {self.status.value}"
            raise ValueError(msg)
        if self.failure and self.failure.is_deterministic:
            msg = "Cannot retry deterministic failure"
            raise ValueError(msg)
        self.status = MissionStatus.PENDING
        self.failure = None

    # --- Task rollup ---

    def all_tasks_completed(self) -> bool:
        return all(t.status == TaskStatus.COMPLETED for t in self.tasks)

    def has_failed_task(self) -> bool:
        return any(t.status == TaskStatus.FAILED for t in self.tasks)

    def next_pending_task(self) -> MissionTask | None:
        for t in sorted(self.tasks, key=lambda t: t.order):
            if t.status == TaskStatus.PENDING:
                return t
        return None

    # --- Serialization ---

    def to_dict(self) -> dict[str, dict[str, object]]:
        d: dict[str, object] = {
            "id": self.mission_id,
            "agent": self.agent,
            "type": self.mission_type,
            "status": self.status.value,
            "priority": self.priority,
            "inputs": self.inputs,
            "acceptance_criteria": self.acceptance_criteria,
            "checklist": self.checklist,
            "created_by": self.created_by,
            "created_at": self.created_at.isoformat(),
        }
        if self.started_at:
            d["started_at"] = self.started_at.isoformat()
        if self.completed_at:
            d["completed_at"] = self.completed_at.isoformat()
        if self.failure:
            d["failure"] = {
                "type": self.failure.error_type,
                "error": self.failure.error_message,
                "retries": self.failure.retries,
                "failed_at": self.failure.failed_at.isoformat(),
            }
        if self.tasks:
            d["tasks"] = [
                {
                    "task_id": t.task_id,
                    "agent": t.agent,
                    "params": t.params,
                    "order": t.order,
                    "status": t.status.value,
                }
                for t in self.tasks
            ]
        return {"mission": d}

    @classmethod
    def from_dict(cls, data: dict[str, dict[str, object]]) -> Mission:
        md = data["mission"]
        tasks = []
        if "tasks" in md:
            for td in md["tasks"]:  # type: ignore[union-attr]
                tasks.append(
                    MissionTask(
                        task_id=td["task_id"],  # type: ignore[index]
                        agent=td["agent"],  # type: ignore[index]
                        params=td["params"],  # type: ignore[index]
                        order=td["order"],  # type: ignore[index]
                        status=TaskStatus(td["status"]),  # type: ignore[index]
                    )
                )
        failure = None
        if "failure" in md:
            fd = md["failure"]  # type: ignore[assignment]
            failure = FailureRecord(
                error_type=fd["type"],  # type: ignore[index]
                error_message=fd["error"],  # type: ignore[index]
                retries=fd["retries"],  # type: ignore[index]
                failed_at=datetime.fromisoformat(fd["failed_at"]),  # type: ignore[index]
            )
        return cls(
            mission_id=str(md["id"]),
            agent=str(md["agent"]),
            mission_type=str(md["type"]),
            status=MissionStatus(str(md["status"])),
            priority=str(md.get("priority", "normal")),  # type: ignore[union-attr]
            inputs=md["inputs"],  # type: ignore[arg-type]
            acceptance_criteria=md["acceptance_criteria"],  # type: ignore[arg-type]
            checklist=md.get("checklist", []),  # type: ignore[union-attr, arg-type]
            created_by=str(md["created_by"]),
            created_at=datetime.fromisoformat(str(md["created_at"])),
            started_at=(
                datetime.fromisoformat(str(md["started_at"]))
                if "started_at" in md
                else None
            ),
            completed_at=(
                datetime.fromisoformat(str(md["completed_at"]))
                if "completed_at" in md
                else None
            ),
            tasks=tasks,
            failure=failure,
        )
