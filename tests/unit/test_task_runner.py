"""Tests for the task runner."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from assistonauts.tasks.runner import (
    Task,
    TaskRunner,
    TaskStatus,
    TransientError,
)
from tests.helpers import FakeLLMClient, FakeResponse

_FAKE_ARTICLE = (
    "---\ntitle: Test\ntype: concept\n---\n\n# Test\n\n## Overview\n\nContent."
)


@pytest.fixture
def workspace(tmp_path: Path) -> Path:
    from assistonauts.storage.workspace import init_workspace

    root = init_workspace(tmp_path)
    # Create a raw source for compiler tasks
    raw_dir = root / "raw" / "articles"
    raw_dir.mkdir(parents=True, exist_ok=True)
    source = raw_dir / "test-source.md"
    source.write_text(
        "---\n"
        "source: test-source.md\n"
        "ingested_by: scout\n"
        "---\n\n"
        "# Test Topic\n\nSome content about testing.\n"
    )
    return root


@pytest.fixture
def tasks_dir(workspace: Path) -> Path:
    d = workspace / ".assistonauts" / "tasks"
    d.mkdir(parents=True, exist_ok=True)
    return d


class TestTaskModel:
    """Test the Task data model."""

    def test_create_task(self) -> None:
        t = Task(
            task_id="t-001",
            agent="compiler",
            params={"source_path": "/some/path.md", "title": "Test"},
        )
        assert t.task_id == "t-001"
        assert t.agent == "compiler"
        assert t.status == TaskStatus.PENDING

    def test_task_status_values(self) -> None:
        assert set(TaskStatus) == {
            TaskStatus.PENDING,
            TaskStatus.RUNNING,
            TaskStatus.COMPLETED,
            TaskStatus.FAILED,
        }


class TestTaskRunner:
    """Test task execution lifecycle."""

    def test_run_task_success(self, workspace: Path, tasks_dir: Path) -> None:
        llm = FakeLLMClient(
            [
                _FAKE_ARTICLE,
                "A summary of the test article.",
            ]
        )
        runner = TaskRunner(workspace_root=workspace, tasks_dir=tasks_dir)
        task = Task(
            task_id="t-001",
            agent="compiler",
            params={
                "source_path": str(workspace / "raw" / "articles" / "test-source.md"),
                "article_type": "concept",
                "title": "Test Topic",
            },
        )
        result = runner.run(task, llm_client=llm)
        assert result.success is True
        assert result.status == TaskStatus.COMPLETED

    def test_run_task_writes_audit_trail(
        self, workspace: Path, tasks_dir: Path
    ) -> None:
        llm = FakeLLMClient(
            [
                _FAKE_ARTICLE,
                "Summary.",
            ]
        )
        runner = TaskRunner(workspace_root=workspace, tasks_dir=tasks_dir)
        task = Task(
            task_id="t-002",
            agent="compiler",
            params={
                "source_path": str(workspace / "raw" / "articles" / "test-source.md"),
                "article_type": "concept",
                "title": "Test Topic",
            },
        )
        runner.run(task, llm_client=llm)
        audit_file = tasks_dir / "t-002.yaml"
        assert audit_file.exists()
        audit = yaml.safe_load(audit_file.read_text())
        assert audit["task_id"] == "t-002"
        assert audit["status"] == "completed"
        assert "started_at" in audit
        assert "completed_at" in audit

    def test_run_task_status_transitions(
        self, workspace: Path, tasks_dir: Path
    ) -> None:
        llm = FakeLLMClient(
            [
                _FAKE_ARTICLE,
                "Summary.",
            ]
        )
        runner = TaskRunner(workspace_root=workspace, tasks_dir=tasks_dir)
        task = Task(
            task_id="t-003",
            agent="compiler",
            params={
                "source_path": str(workspace / "raw" / "articles" / "test-source.md"),
                "article_type": "concept",
                "title": "Test Topic",
            },
        )
        runner.run(task, llm_client=llm)
        assert task.status == TaskStatus.COMPLETED

    def test_run_task_deterministic_failure(
        self, workspace: Path, tasks_dir: Path
    ) -> None:
        """Deterministic errors (bad input) should fail-fast, no retry."""
        llm = FakeLLMClient()
        runner = TaskRunner(workspace_root=workspace, tasks_dir=tasks_dir)
        task = Task(
            task_id="t-004",
            agent="compiler",
            params={
                "source_path": "/nonexistent/path.md",
                "article_type": "concept",
                "title": "Bad Source",
            },
        )
        result = runner.run(task, llm_client=llm)
        assert result.success is False
        assert result.status == TaskStatus.FAILED
        assert result.error_type == "deterministic"
        # Audit trail should record the failure
        audit_file = tasks_dir / "t-004.yaml"
        assert audit_file.exists()
        audit = yaml.safe_load(audit_file.read_text())
        assert audit["status"] == "failed"
        assert audit["error_type"] == "deterministic"

    def test_run_task_transient_failure_retries(
        self, workspace: Path, tasks_dir: Path
    ) -> None:
        """Transient errors should be retried."""

        call_count = 0

        class FailThenSucceedLLM:
            def complete(
                self,
                messages: list[dict[str, str]],
                model: str | None = None,
                system: str | None = None,
                **kwargs: object,
            ) -> FakeResponse:
                nonlocal call_count
                call_count += 1
                if call_count <= 2:
                    raise TransientError("API timeout")
                return FakeResponse(
                    "---\ntitle: T\ntype: concept\n---\n\n# T\n\n## Overview\n\nC."
                )

        runner = TaskRunner(
            workspace_root=workspace,
            tasks_dir=tasks_dir,
            max_retries=3,
        )
        task = Task(
            task_id="t-005",
            agent="compiler",
            params={
                "source_path": str(workspace / "raw" / "articles" / "test-source.md"),
                "article_type": "concept",
                "title": "Retry Test",
            },
        )
        result = runner.run(task, llm_client=FailThenSucceedLLM())
        assert result.success is True
        assert result.retry_count == 2

    def test_run_task_transient_exhausted(
        self, workspace: Path, tasks_dir: Path
    ) -> None:
        """Transient errors that exhaust retries should fail."""

        class AlwaysFailLLM:
            def complete(
                self,
                messages: list[dict[str, str]],
                model: str | None = None,
                system: str | None = None,
                **kwargs: object,
            ) -> FakeResponse:
                raise TransientError("API timeout")

        runner = TaskRunner(
            workspace_root=workspace,
            tasks_dir=tasks_dir,
            max_retries=2,
        )
        task = Task(
            task_id="t-006",
            agent="compiler",
            params={
                "source_path": str(workspace / "raw" / "articles" / "test-source.md"),
                "article_type": "concept",
                "title": "Exhaust Test",
            },
        )
        result = runner.run(task, llm_client=AlwaysFailLLM())
        assert result.success is False
        assert result.status == TaskStatus.FAILED
        assert result.error_type == "transient"
        assert result.retry_count == 2

    def test_task_result_includes_agent_output(
        self, workspace: Path, tasks_dir: Path
    ) -> None:
        llm = FakeLLMClient(
            [
                _FAKE_ARTICLE,
                "Summary of test.",
            ]
        )
        runner = TaskRunner(workspace_root=workspace, tasks_dir=tasks_dir)
        task = Task(
            task_id="t-007",
            agent="compiler",
            params={
                "source_path": str(workspace / "raw" / "articles" / "test-source.md"),
                "article_type": "concept",
                "title": "Test Topic",
            },
        )
        result = runner.run(task, llm_client=llm)
        assert result.agent_output is not None
