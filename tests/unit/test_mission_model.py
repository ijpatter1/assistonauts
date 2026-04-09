"""Tests for the Mission model and state machine."""

from datetime import datetime

import pytest

from assistonauts.missions.models import (
    FailureRecord,
    Mission,
    MissionStatus,
    MissionTask,
)
from assistonauts.tasks.runner import TaskStatus

# --- MissionStatus enum ---


class TestMissionStatus:
    def test_all_states_exist(self) -> None:
        assert MissionStatus.PENDING.value == "pending"
        assert MissionStatus.RUNNING.value == "running"
        assert MissionStatus.COMPLETED.value == "completed"
        assert MissionStatus.FAILED.value == "failed"
        assert MissionStatus.STALE.value == "stale"

    def test_from_string(self) -> None:
        assert MissionStatus("pending") == MissionStatus.PENDING
        assert MissionStatus("stale") == MissionStatus.STALE


# --- MissionTask (reference to a Task within a mission) ---


class TestMissionTask:
    def test_creation(self) -> None:
        mt = MissionTask(
            task_id="task-001",
            agent="compiler",
            params={"source": "raw/papers/test.md", "title": "Test"},
            order=0,
        )
        assert mt.task_id == "task-001"
        assert mt.agent == "compiler"
        assert mt.order == 0
        assert mt.status == TaskStatus.PENDING

    def test_ordering(self) -> None:
        t1 = MissionTask(task_id="t1", agent="scout", params={}, order=0)
        t2 = MissionTask(task_id="t2", agent="compiler", params={}, order=1)
        t3 = MissionTask(task_id="t3", agent="compiler", params={}, order=2)
        assert sorted([t3, t1, t2], key=lambda t: t.order) == [t1, t2, t3]


# --- Mission model ---


class TestMissionCreation:
    def test_defaults(self) -> None:
        m = Mission(
            mission_id="mission-0001",
            agent="compiler",
            mission_type="compile_article",
            inputs={"sources": ["raw/papers/test.md"]},
            acceptance_criteria=["Article written", "Summary generated"],
            created_by="captain",
        )
        assert m.mission_id == "mission-0001"
        assert m.agent == "compiler"
        assert m.mission_type == "compile_article"
        assert m.status == MissionStatus.PENDING
        assert m.priority == "normal"
        assert m.checklist == []
        assert m.tasks == []
        assert m.created_by == "captain"
        assert isinstance(m.created_at, datetime)

    def test_with_priority(self) -> None:
        m = Mission(
            mission_id="m-002",
            agent="scout",
            mission_type="ingest_sources",
            inputs={"paths": ["/tmp/a.pdf"]},
            acceptance_criteria=["Sources ingested"],
            created_by="captain",
            priority="high",
        )
        assert m.priority == "high"

    def test_with_tasks(self) -> None:
        tasks = [
            MissionTask(
                task_id="t1",
                agent="compiler",
                params={"source": "a.md"},
                order=0,
            ),
            MissionTask(
                task_id="t2",
                agent="compiler",
                params={"source": "b.md"},
                order=1,
            ),
        ]
        m = Mission(
            mission_id="m-003",
            agent="compiler",
            mission_type="compile_batch",
            inputs={"sources": ["a.md", "b.md"]},
            acceptance_criteria=["All compiled"],
            created_by="captain",
            tasks=tasks,
        )
        assert len(m.tasks) == 2
        assert m.tasks[0].task_id == "t1"


# --- State transitions ---


class TestMissionStateTransitions:
    def _make_mission(self, status: MissionStatus = MissionStatus.PENDING) -> Mission:
        m = Mission(
            mission_id="m-test",
            agent="compiler",
            mission_type="compile_article",
            inputs={},
            acceptance_criteria=["Done"],
            created_by="captain",
        )
        m.status = status
        return m

    def test_pending_to_running(self) -> None:
        m = self._make_mission(MissionStatus.PENDING)
        m.start()
        assert m.status == MissionStatus.RUNNING
        assert m.started_at is not None

    def test_running_to_completed(self) -> None:
        m = self._make_mission(MissionStatus.PENDING)
        m.start()
        m.complete()
        assert m.status == MissionStatus.COMPLETED
        assert m.completed_at is not None

    def test_running_to_failed_deterministic(self) -> None:
        m = self._make_mission(MissionStatus.PENDING)
        m.start()
        m.fail(error_type="deterministic", error_message="Context overflow")
        assert m.status == MissionStatus.FAILED
        assert m.failure is not None
        assert m.failure.error_type == "deterministic"
        assert m.failure.error_message == "Context overflow"
        assert m.failure.retries == 0

    def test_running_to_failed_transient(self) -> None:
        m = self._make_mission(MissionStatus.PENDING)
        m.start()
        m.fail(error_type="transient", error_message="API timeout", retries=2)
        assert m.status == MissionStatus.FAILED
        assert m.failure is not None
        assert m.failure.retries == 2

    def test_completed_to_stale(self) -> None:
        m = self._make_mission(MissionStatus.PENDING)
        m.start()
        m.complete()
        m.mark_stale(reason="Input source changed")
        assert m.status == MissionStatus.STALE

    def test_cannot_start_non_pending(self) -> None:
        m = self._make_mission(MissionStatus.COMPLETED)
        with pytest.raises(ValueError, match="Cannot start"):
            m.start()

    def test_cannot_complete_non_running(self) -> None:
        m = self._make_mission(MissionStatus.PENDING)
        with pytest.raises(ValueError, match="Cannot complete"):
            m.complete()

    def test_cannot_fail_non_running(self) -> None:
        m = self._make_mission(MissionStatus.COMPLETED)
        with pytest.raises(ValueError, match="Cannot fail"):
            m.fail(error_type="deterministic", error_message="bad")

    def test_cannot_stale_non_completed(self) -> None:
        m = self._make_mission(MissionStatus.RUNNING)
        with pytest.raises(ValueError, match="Cannot mark stale"):
            m.mark_stale(reason="changed")

    def test_failed_transient_can_retry(self) -> None:
        """Transient failures return to PENDING for retry."""
        m = self._make_mission(MissionStatus.PENDING)
        m.start()
        m.fail(error_type="transient", error_message="timeout", retries=1)
        m.retry()
        assert m.status == MissionStatus.PENDING

    def test_failed_deterministic_cannot_retry(self) -> None:
        m = self._make_mission(MissionStatus.PENDING)
        m.start()
        m.fail(error_type="deterministic", error_message="overflow")
        with pytest.raises(ValueError, match="Cannot retry deterministic"):
            m.retry()


# --- Failure record ---


class TestFailureRecord:
    def test_creation(self) -> None:
        f = FailureRecord(
            error_type="transient",
            error_message="API timeout after 30s",
            retries=2,
        )
        assert f.error_type == "transient"
        assert isinstance(f.failed_at, datetime)

    def test_is_deterministic(self) -> None:
        f = FailureRecord(error_type="deterministic", error_message="bad input")
        assert f.is_deterministic
        f2 = FailureRecord(error_type="transient", error_message="timeout")
        assert not f2.is_deterministic


# --- Task failure rollup ---


class TestTaskFailureRollup:
    def _make_mission_with_tasks(self) -> Mission:
        tasks = [
            MissionTask(task_id="t1", agent="compiler", params={}, order=0),
            MissionTask(task_id="t2", agent="compiler", params={}, order=1),
            MissionTask(task_id="t3", agent="compiler", params={}, order=2),
        ]
        return Mission(
            mission_id="m-rollup",
            agent="compiler",
            mission_type="compile_batch",
            inputs={},
            acceptance_criteria=["All compiled"],
            created_by="captain",
            tasks=tasks,
        )

    def test_all_tasks_completed(self) -> None:
        m = self._make_mission_with_tasks()
        for t in m.tasks:
            t.status = TaskStatus.COMPLETED
        assert m.all_tasks_completed()

    def test_not_all_tasks_completed(self) -> None:
        m = self._make_mission_with_tasks()
        m.tasks[0].status = TaskStatus.COMPLETED
        m.tasks[1].status = TaskStatus.RUNNING
        assert not m.all_tasks_completed()

    def test_has_failed_task(self) -> None:
        m = self._make_mission_with_tasks()
        m.tasks[1].status = TaskStatus.FAILED
        assert m.has_failed_task()

    def test_no_failed_tasks(self) -> None:
        m = self._make_mission_with_tasks()
        assert not m.has_failed_task()

    def test_next_pending_task(self) -> None:
        m = self._make_mission_with_tasks()
        m.tasks[0].status = TaskStatus.COMPLETED
        nxt = m.next_pending_task()
        assert nxt is not None
        assert nxt.task_id == "t2"

    def test_next_pending_task_none_when_all_done(self) -> None:
        m = self._make_mission_with_tasks()
        for t in m.tasks:
            t.status = TaskStatus.COMPLETED
        assert m.next_pending_task() is None


# --- Serialization ---


class TestMissionSerialization:
    def test_to_dict(self) -> None:
        m = Mission(
            mission_id="m-ser",
            agent="compiler",
            mission_type="compile_article",
            inputs={"sources": ["a.md"]},
            acceptance_criteria=["Article written"],
            created_by="captain",
            priority="high",
        )
        d = m.to_dict()
        assert d["mission"]["id"] == "m-ser"
        assert d["mission"]["agent"] == "compiler"
        assert d["mission"]["type"] == "compile_article"
        assert d["mission"]["status"] == "pending"
        assert d["mission"]["priority"] == "high"
        assert d["mission"]["inputs"] == {"sources": ["a.md"]}
        assert d["mission"]["acceptance_criteria"] == ["Article written"]
        assert d["mission"]["created_by"] == "captain"
        assert "created_at" in d["mission"]

    def test_to_dict_with_failure(self) -> None:
        m = Mission(
            mission_id="m-fail",
            agent="compiler",
            mission_type="compile_article",
            inputs={},
            acceptance_criteria=[],
            created_by="captain",
        )
        m.start()
        m.fail(error_type="deterministic", error_message="Context overflow")
        d = m.to_dict()
        assert "failure" in d["mission"]
        assert d["mission"]["failure"]["type"] == "deterministic"
        assert d["mission"]["failure"]["error"] == "Context overflow"

    def test_from_dict_roundtrip(self) -> None:
        m = Mission(
            mission_id="m-rt",
            agent="scout",
            mission_type="ingest_sources",
            inputs={"paths": ["/tmp/a.pdf"]},
            acceptance_criteria=["Ingested"],
            created_by="captain",
            priority="high",
        )
        d = m.to_dict()
        m2 = Mission.from_dict(d)
        assert m2.mission_id == m.mission_id
        assert m2.agent == m.agent
        assert m2.mission_type == m.mission_type
        assert m2.status == m.status
        assert m2.priority == m.priority
        assert m2.inputs == m.inputs
        assert m2.acceptance_criteria == m.acceptance_criteria
        assert m2.created_by == m.created_by

    def test_from_dict_with_tasks(self) -> None:
        m = Mission(
            mission_id="m-tasks",
            agent="compiler",
            mission_type="compile_batch",
            inputs={},
            acceptance_criteria=[],
            created_by="captain",
            tasks=[
                MissionTask(task_id="t1", agent="compiler", params={"x": "1"}, order=0),
            ],
        )
        d = m.to_dict()
        m2 = Mission.from_dict(d)
        assert len(m2.tasks) == 1
        assert m2.tasks[0].task_id == "t1"
        assert m2.tasks[0].order == 0

    def test_stale_reason_roundtrip(self) -> None:
        m = Mission(
            mission_id="m-stale",
            agent="compiler",
            mission_type="compile",
            inputs={},
            acceptance_criteria=[],
            created_by="captain",
        )
        m.start()
        m.complete()
        m.mark_stale(reason="Source file changed")
        d = m.to_dict()
        m2 = Mission.from_dict(d)
        assert m2.status == MissionStatus.STALE
        assert m2.stale_reason == "Source file changed"

    def test_verified_by_in_complete(self) -> None:
        m = Mission(
            mission_id="m-verify",
            agent="compiler",
            mission_type="compile",
            inputs={},
            acceptance_criteria=["Article written"],
            created_by="captain",
        )
        m.start()
        m.complete(verified_by="captain")
        assert "verified_by:captain" in m.checklist

    def test_failure_record_roundtrip(self) -> None:
        m = Mission(
            mission_id="m-fail-rt",
            agent="compiler",
            mission_type="compile",
            inputs={},
            acceptance_criteria=[],
            created_by="captain",
        )
        m.start()
        m.fail(
            error_type="deterministic",
            error_message="Context overflow: 210K tokens",
            retries=0,
        )
        d = m.to_dict()
        m2 = Mission.from_dict(d)
        assert m2.status == MissionStatus.FAILED
        assert m2.failure is not None
        assert m2.failure.error_type == "deterministic"
        assert m2.failure.error_message == "Context overflow: 210K tokens"
        assert m2.failure.retries == 0
        assert m2.failure.failed_at is not None

    def test_started_at_preserved_on_retry(self) -> None:
        m = Mission(
            mission_id="m-retry",
            agent="scout",
            mission_type="ingest",
            inputs={},
            acceptance_criteria=[],
            created_by="captain",
        )
        m.start()
        original_started = m.started_at
        m.fail(error_type="transient", error_message="timeout")
        m.retry()
        m.start()
        assert m.started_at == original_started
