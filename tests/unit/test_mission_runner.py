"""Tests for the mission runner."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import pytest
import yaml

from assistonauts.missions.runner import (
    Mission,
    MissionResult,
    MissionRunner,
    MissionStatus,
    TransientError,
)


class FakeResponse:
    def __init__(self, content: str) -> None:
        self.content = content
        self.model = "fake-model"
        self.usage = {"prompt_tokens": 10, "completion_tokens": 5}


class FakeLLMClient:
    def __init__(self, responses: list[str] | None = None) -> None:
        self._responses = list(responses or ["default response"])
        self._call_count = 0

    def complete(
        self,
        messages: list[dict[str, str]],
        model: str | None = None,
        system: str | None = None,
        **kwargs: object,
    ) -> FakeResponse:
        idx = min(self._call_count, len(self._responses) - 1)
        self._call_count += 1
        return FakeResponse(self._responses[idx])


@pytest.fixture
def workspace(tmp_path: Path) -> Path:
    from assistonauts.storage.workspace import init_workspace

    root = init_workspace(tmp_path)
    # Create a raw source for compiler missions
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
def missions_dir(workspace: Path) -> Path:
    d = workspace / ".assistonauts" / "missions"
    d.mkdir(parents=True, exist_ok=True)
    return d


class TestMissionModel:
    """Test the Mission data model."""

    def test_create_mission(self) -> None:
        m = Mission(
            mission_id="m-001",
            agent="compiler",
            params={"source_path": "/some/path.md", "title": "Test"},
        )
        assert m.mission_id == "m-001"
        assert m.agent == "compiler"
        assert m.status == MissionStatus.PENDING

    def test_mission_status_values(self) -> None:
        assert set(MissionStatus) == {
            MissionStatus.PENDING,
            MissionStatus.RUNNING,
            MissionStatus.COMPLETED,
            MissionStatus.FAILED,
        }


class TestMissionRunner:
    """Test mission execution lifecycle."""

    def test_run_mission_success(self, workspace: Path, missions_dir: Path) -> None:
        llm = FakeLLMClient([
            "---\ntitle: Test\ntype: concept\n---\n\n# Test\n\n## Overview\n\nContent.",
            "A summary of the test article.",
        ])
        runner = MissionRunner(workspace_root=workspace, missions_dir=missions_dir)
        mission = Mission(
            mission_id="m-001",
            agent="compiler",
            params={
                "source_path": str(workspace / "raw" / "articles" / "test-source.md"),
                "article_type": "concept",
                "title": "Test Topic",
            },
        )
        result = runner.run(mission, llm_client=llm)
        assert result.success is True
        assert result.status == MissionStatus.COMPLETED

    def test_run_mission_writes_audit_trail(
        self, workspace: Path, missions_dir: Path
    ) -> None:
        llm = FakeLLMClient([
            "---\ntitle: Test\ntype: concept\n---\n\n# Test\n\n## Overview\n\nContent.",
            "Summary.",
        ])
        runner = MissionRunner(workspace_root=workspace, missions_dir=missions_dir)
        mission = Mission(
            mission_id="m-002",
            agent="compiler",
            params={
                "source_path": str(workspace / "raw" / "articles" / "test-source.md"),
                "article_type": "concept",
                "title": "Test Topic",
            },
        )
        runner.run(mission, llm_client=llm)
        audit_file = missions_dir / "m-002.yaml"
        assert audit_file.exists()
        audit = yaml.safe_load(audit_file.read_text())
        assert audit["mission_id"] == "m-002"
        assert audit["status"] == "completed"
        assert "started_at" in audit
        assert "completed_at" in audit

    def test_run_mission_status_transitions(
        self, workspace: Path, missions_dir: Path
    ) -> None:
        llm = FakeLLMClient([
            "---\ntitle: Test\ntype: concept\n---\n\n# Test\n\n## Overview\n\nContent.",
            "Summary.",
        ])
        runner = MissionRunner(workspace_root=workspace, missions_dir=missions_dir)
        mission = Mission(
            mission_id="m-003",
            agent="compiler",
            params={
                "source_path": str(workspace / "raw" / "articles" / "test-source.md"),
                "article_type": "concept",
                "title": "Test Topic",
            },
        )
        result = runner.run(mission, llm_client=llm)
        assert mission.status == MissionStatus.COMPLETED

    def test_run_mission_deterministic_failure(
        self, workspace: Path, missions_dir: Path
    ) -> None:
        """Deterministic errors (bad input) should fail-fast, no retry."""
        llm = FakeLLMClient()
        runner = MissionRunner(workspace_root=workspace, missions_dir=missions_dir)
        mission = Mission(
            mission_id="m-004",
            agent="compiler",
            params={
                "source_path": "/nonexistent/path.md",
                "article_type": "concept",
                "title": "Bad Source",
            },
        )
        result = runner.run(mission, llm_client=llm)
        assert result.success is False
        assert result.status == MissionStatus.FAILED
        assert result.error_type == "deterministic"
        # Audit trail should record the failure
        audit_file = missions_dir / "m-004.yaml"
        assert audit_file.exists()
        audit = yaml.safe_load(audit_file.read_text())
        assert audit["status"] == "failed"
        assert audit["error_type"] == "deterministic"

    def test_run_mission_transient_failure_retries(
        self, workspace: Path, missions_dir: Path
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

        runner = MissionRunner(
            workspace_root=workspace,
            missions_dir=missions_dir,
            max_retries=3,
        )
        mission = Mission(
            mission_id="m-005",
            agent="compiler",
            params={
                "source_path": str(workspace / "raw" / "articles" / "test-source.md"),
                "article_type": "concept",
                "title": "Retry Test",
            },
        )
        result = runner.run(mission, llm_client=FailThenSucceedLLM())
        assert result.success is True
        assert result.retry_count == 2

    def test_run_mission_transient_exhausted(
        self, workspace: Path, missions_dir: Path
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

        runner = MissionRunner(
            workspace_root=workspace,
            missions_dir=missions_dir,
            max_retries=2,
        )
        mission = Mission(
            mission_id="m-006",
            agent="compiler",
            params={
                "source_path": str(workspace / "raw" / "articles" / "test-source.md"),
                "article_type": "concept",
                "title": "Exhaust Test",
            },
        )
        result = runner.run(mission, llm_client=AlwaysFailLLM())
        assert result.success is False
        assert result.status == MissionStatus.FAILED
        assert result.error_type == "transient"
        assert result.retry_count == 2

    def test_mission_result_includes_agent_output(
        self, workspace: Path, missions_dir: Path
    ) -> None:
        llm = FakeLLMClient([
            "---\ntitle: Test\ntype: concept\n---\n\n# Test\n\n## Overview\n\nContent.",
            "Summary of test.",
        ])
        runner = MissionRunner(workspace_root=workspace, missions_dir=missions_dir)
        mission = Mission(
            mission_id="m-007",
            agent="compiler",
            params={
                "source_path": str(workspace / "raw" / "articles" / "test-source.md"),
                "article_type": "concept",
                "title": "Test Topic",
            },
        )
        result = runner.run(mission, llm_client=llm)
        assert result.agent_output is not None
