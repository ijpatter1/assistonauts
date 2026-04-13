"""Tests for UAT root cause fixes: verification, curator init, indexing.

Covers the three systemic issues found during Phase 5 UAT:
1. Verification snippet too short (20 lines) → Captain rejects valid articles
2. TaskRunner ignores agent_output.success → curator failures silently pass
3. Curator created without Archivist → cross_reference is a no-op
4. No indexing before Refinement → empty retrieval results
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import pytest

from assistonauts.agents.base import AgentResult
from assistonauts.expeditions.orchestrator import (
    BuildOrchestrator,
    IterationPhase,
)
from assistonauts.missions.models import Mission
from assistonauts.models.config import ExpeditionConfig
from assistonauts.tasks.runner import Task, TaskRunner, TaskStatus
from tests.helpers import FakeLLMClient


@pytest.fixture()
def workspace(tmp_path: Path) -> Path:
    dirs = [
        "raw/articles",
        "wiki/concept",
        "wiki/explorations",
        "index",
        "audits",
        "expeditions/test-exp/missions",
        "expeditions/test-exp/review",
        "station-logs",
        ".assistonauts/logs",
        ".assistonauts/tasks",
    ]
    for d in dirs:
        (tmp_path / d).mkdir(parents=True)
    return tmp_path


@pytest.fixture()
def config() -> ExpeditionConfig:
    return ExpeditionConfig.from_dict(
        {
            "name": "test-exp",
            "description": "Test expedition",
            "scope": {
                "description": "Test scope",
                "keywords": ["test"],
            },
            "sources": {
                "local": [{"path": "/tmp/test", "pattern": "*.md"}],
            },
        }
    )


# ── Fix 1: Verification snippet size ──────────────────


class TestVerificationSnippetSize:
    """Verification should read enough of the article for the Captain
    to judge acceptance criteria about specific content."""

    def test_snippet_default_is_80_lines(
        self,
        workspace: Path,
        config: ExpeditionConfig,
    ) -> None:
        """Articles up to 80 lines are fully visible in verification."""
        # Create a 60-line article
        lines = ["---", "title: Test", "type: concept", "---", ""]
        lines += [f"Line {i}" for i in range(55)]
        article = workspace / "wiki" / "concept" / "test.md"
        article.write_text("\n".join(lines))

        client = FakeLLMClient(responses=["VERIFIED"])
        orch = BuildOrchestrator(
            workspace_root=workspace,
            config=config,
            llm_client=client,
        )
        mission = Mission(
            mission_id="m-snip",
            agent="compiler",
            mission_type="compile_article",
            inputs={},
            acceptance_criteria=["Includes Line 50"],
            created_by="captain",
        )
        orch._verify_mission(
            mission,
            task_output_paths=[str(article)],
        )
        prompt = client.calls[0]["messages"][0]["content"]
        # Line 50 should be visible with 80-line default
        assert "Line 50" in prompt

    def test_20_line_snippet_would_miss_content(
        self,
        workspace: Path,
        config: ExpeditionConfig,
    ) -> None:
        """A 20-line snippet would miss content at line 50 — confirms
        the old default was insufficient."""
        lines = ["---", "title: Test", "type: concept", "---", ""]
        lines += [f"Line {i}" for i in range(55)]
        article = workspace / "wiki" / "concept" / "test.md"
        article.write_text("\n".join(lines))

        client = FakeLLMClient(responses=["VERIFIED"])
        orch = BuildOrchestrator(
            workspace_root=workspace,
            config=config,
            llm_client=client,
        )
        # Read only 20 lines explicitly to prove the old behavior was broken
        snippet = orch._read_output_snippets(
            [str(article)], max_lines=20
        )
        assert "Line 50" not in snippet


# ── Fix 2: Lenient verification prompt ────────────────


class TestLenientVerification:
    """Verification prompt should guide Captain to accept draft content."""

    def test_verification_prompt_mentions_draft_leniency(
        self,
        workspace: Path,
        config: ExpeditionConfig,
    ) -> None:
        """The verification prompt tells Captain that minor gaps are OK."""
        client = FakeLLMClient(responses=["VERIFIED"])
        orch = BuildOrchestrator(
            workspace_root=workspace,
            config=config,
            llm_client=client,
        )
        mission = Mission(
            mission_id="m-lenient",
            agent="compiler",
            mission_type="compile_article",
            inputs={},
            acceptance_criteria=["Some criterion"],
            created_by="captain",
        )
        orch._verify_mission(mission)
        prompt = client.calls[0]["messages"][0]["content"]
        assert "draft" in prompt.lower()
        assert "minor gaps" in prompt.lower() or "reasonable attempt" in prompt.lower()


# ── Fix 3: TaskRunner checks agent_output.success ─────


@dataclass
class FakeFailResult:
    """Agent result that reports success=False."""

    success: bool = False
    output_path: Path | None = None
    output_paths: list[Path] = field(default_factory=list)
    message: str = "Agent reported failure"


@dataclass
class FakeSuccessResult:
    """Agent result that reports success=True."""

    success: bool = True
    output_path: Path | None = None
    output_paths: list[Path] = field(default_factory=list)
    message: str = "OK"


class FakeFailAgent:
    """Agent whose run_task returns success=False without raising."""

    role = "fake"

    def run_task(self, params: dict[str, str]) -> FakeFailResult:
        return FakeFailResult()

    def close(self) -> None:
        pass


class FakeSuccessAgent:
    """Agent whose run_task returns success=True."""

    role = "fake"

    def run_task(self, params: dict[str, str]) -> FakeSuccessResult:
        return FakeSuccessResult()

    def close(self) -> None:
        pass


class TestTaskRunnerChecksAgentSuccess:
    """TaskRunner must treat agent_output.success=False as a failure,
    not silently mark the task as completed."""

    def test_agent_output_success_false_fails_task(
        self,
        workspace: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """When an agent returns success=False, TaskRunner should
        report task failure."""
        from assistonauts.tasks import runner as runner_mod

        monkeypatch.setattr(
            runner_mod,
            "_resolve_agent",
            lambda *a, **kw: FakeFailAgent(),
        )

        tasks_dir = workspace / ".assistonauts" / "tasks"
        runner = TaskRunner(workspace_root=workspace, tasks_dir=tasks_dir)
        task = Task(
            task_id="t-fail-check",
            agent="curator",
            params={"article_path": "wiki/concept/test.md"},
        )
        result = runner.run(task, llm_client=FakeLLMClient())

        assert result.success is False
        assert result.status == TaskStatus.FAILED
        assert "failure" in result.error_message.lower() or "failed" in result.error_message.lower() or "Agent reported" in result.error_message

    def test_agent_output_success_true_passes_task(
        self,
        workspace: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """When an agent returns success=True, TaskRunner marks completed."""
        from assistonauts.tasks import runner as runner_mod

        monkeypatch.setattr(
            runner_mod,
            "_resolve_agent",
            lambda *a, **kw: FakeSuccessAgent(),
        )

        tasks_dir = workspace / ".assistonauts" / "tasks"
        runner = TaskRunner(workspace_root=workspace, tasks_dir=tasks_dir)
        task = Task(
            task_id="t-pass-check",
            agent="curator",
            params={"article_path": "wiki/concept/test.md"},
        )
        result = runner.run(task, llm_client=FakeLLMClient())

        assert result.success is True
        assert result.status == TaskStatus.COMPLETED


# ── Fix 4: Curator gets Archivist via agent_context ───


class TestCuratorAgentContext:
    """TaskRunner should pass archivist and embedding_client to
    CuratorAgent when agent_context is provided."""

    def test_curator_receives_archivist(
        self,
        workspace: Path,
    ) -> None:
        """CuratorAgent created via _resolve_agent gets the archivist."""
        from assistonauts.agents.curator import CuratorAgent
        from assistonauts.archivist.service import Archivist
        from assistonauts.tasks.runner import _resolve_agent

        CuratorAgent._active_instance = None  # Reset singleton

        archivist = Archivist(workspace, embedding_dimensions=4)
        ctx = {"archivist": archivist, "embedding_client": None}
        agent = _resolve_agent(
            "curator", workspace, FakeLLMClient(), agent_context=ctx
        )
        try:
            assert isinstance(agent, CuratorAgent)
            assert agent._archivist is archivist
        finally:
            agent.close()

    def test_curator_without_context_gets_none(
        self,
        workspace: Path,
    ) -> None:
        """CuratorAgent created without agent_context has None archivist."""
        from assistonauts.agents.curator import CuratorAgent
        from assistonauts.tasks.runner import _resolve_agent

        CuratorAgent._active_instance = None

        agent = _resolve_agent("curator", workspace, FakeLLMClient())
        try:
            assert isinstance(agent, CuratorAgent)
            assert agent._archivist is None
        finally:
            agent.close()


# ── Fix 5: Indexing before Refinement ─────────────────


class TestIndexingBeforeRefinement:
    """The orchestrator must index wiki articles before running
    Refinement iterations, so the Curator can find them."""

    def test_index_wiki_articles_indexes_existing(
        self,
        workspace: Path,
        config: ExpeditionConfig,
    ) -> None:
        """_index_wiki_articles should index articles into the Archivist."""
        # Create a wiki article
        article_dir = workspace / "wiki" / "concept"
        article_dir.mkdir(parents=True, exist_ok=True)
        (article_dir / "test-article.md").write_text(
            "---\ntitle: Test Article\ntype: concept\n---\n\n"
            "# Test Article\n\n## Overview\n\nSome test content.\n"
        )

        client = FakeLLMClient()
        orch = BuildOrchestrator(
            workspace_root=workspace,
            config=config,
            llm_client=client,
        )

        # Before indexing — no articles in archivist
        articles_before = orch.archivist.db.list_articles()
        assert len(articles_before) == 0

        orch._index_wiki_articles()

        # After indexing — article should be found
        articles_after = orch.archivist.db.list_articles()
        assert len(articles_after) == 1
        assert articles_after[0]["path"] == "wiki/concept/test-article.md"

    def test_index_wiki_articles_no_wiki_dir(
        self,
        workspace: Path,
        config: ExpeditionConfig,
    ) -> None:
        """_index_wiki_articles handles missing wiki/ gracefully."""
        import shutil

        shutil.rmtree(workspace / "wiki", ignore_errors=True)

        client = FakeLLMClient()
        orch = BuildOrchestrator(
            workspace_root=workspace,
            config=config,
            llm_client=client,
        )
        # Should not raise
        orch._index_wiki_articles()

    def test_orchestrator_has_archivist(
        self,
        workspace: Path,
        config: ExpeditionConfig,
    ) -> None:
        """BuildOrchestrator creates an Archivist instance."""
        client = FakeLLMClient()
        orch = BuildOrchestrator(
            workspace_root=workspace,
            config=config,
            llm_client=client,
        )
        assert orch.archivist is not None
        assert hasattr(orch.archivist, "index")


# ── Fix 6: Auto-approve structural mission types ─────


class TestAutoApproveStructuralMissions:
    """Curator cross_reference and Scout ingest_sources missions should
    be auto-approved — Captain verification adds no value for structural
    operations and actively harms success rate by applying content criteria
    to non-content operations."""

    def test_cross_reference_auto_approved(
        self,
        workspace: Path,
        config: ExpeditionConfig,
    ) -> None:
        """cross_reference missions are auto-approved without LLM call."""
        client = FakeLLMClient(responses=[])
        orch = BuildOrchestrator(
            workspace_root=workspace,
            config=config,
            llm_client=client,
        )
        mission = Mission(
            mission_id="m-curator-001",
            agent="curator",
            mission_type="cross_reference",
            inputs={"article_path": "wiki/concept/test.md"},
            acceptance_criteria=["Links added", "No broken links"],
            created_by="captain",
        )
        assert orch._verify_mission(mission) is True
        # No LLM call made
        assert len(client.calls) == 0

    def test_ingest_sources_auto_approved(
        self,
        workspace: Path,
        config: ExpeditionConfig,
    ) -> None:
        """ingest_sources missions are auto-approved."""
        client = FakeLLMClient(responses=[])
        orch = BuildOrchestrator(
            workspace_root=workspace,
            config=config,
            llm_client=client,
        )
        mission = Mission(
            mission_id="m-scout-001",
            agent="scout",
            mission_type="ingest_sources",
            inputs={},
            acceptance_criteria=["Sources ingested"],
            created_by="captain",
        )
        assert orch._verify_mission(mission) is True
        assert len(client.calls) == 0

    def test_compile_article_still_verified(
        self,
        workspace: Path,
        config: ExpeditionConfig,
    ) -> None:
        """compile_article missions are NOT auto-approved — content quality
        benefits from Captain verification."""
        client = FakeLLMClient(responses=["VERIFIED"])
        orch = BuildOrchestrator(
            workspace_root=workspace,
            config=config,
            llm_client=client,
        )
        mission = Mission(
            mission_id="m-compile-001",
            agent="compiler",
            mission_type="compile_article",
            inputs={},
            acceptance_criteria=["Article compiled"],
            created_by="captain",
        )
        orch._verify_mission(mission)
        # LLM call WAS made for compile_article
        assert len(client.calls) == 1


# ── Fix 7: Verification retry with feedback ──────────


class TestVerificationRetryWithFeedback:
    """Captain verification uses a retry-with-feedback loop to handle
    LLM non-determinism. If the Captain rejects, the rejection reason
    is fed back for reconsideration before failing the mission."""

    def test_verified_on_first_attempt_no_retry(
        self,
        workspace: Path,
        config: ExpeditionConfig,
    ) -> None:
        """When Captain says VERIFIED on first try, no retry needed."""
        client = FakeLLMClient(responses=["VERIFIED — all good"])
        orch = BuildOrchestrator(
            workspace_root=workspace,
            config=config,
            llm_client=client,
        )
        mission = Mission(
            mission_id="m-v1",
            agent="compiler",
            mission_type="compile_article",
            inputs={},
            acceptance_criteria=["Article compiled"],
            created_by="captain",
        )
        assert orch._verify_mission(mission) is True
        assert len(client.calls) == 1

    def test_rejected_then_verified_on_retry(
        self,
        workspace: Path,
        config: ExpeditionConfig,
    ) -> None:
        """First attempt rejects, retry with feedback succeeds."""
        client = FakeLLMClient(
            responses=[
                "REJECTED — missing publisher info",
                "VERIFIED — reconsidering, the source material was limited",
            ]
        )
        orch = BuildOrchestrator(
            workspace_root=workspace,
            config=config,
            llm_client=client,
        )
        mission = Mission(
            mission_id="m-v2",
            agent="compiler",
            mission_type="compile_article",
            inputs={},
            acceptance_criteria=["Include publisher info"],
            created_by="captain",
        )
        assert orch._verify_mission(mission) is True
        # 2 LLM calls: initial rejection + retry
        assert len(client.calls) == 2

    def test_retry_feedback_includes_rejection_reason(
        self,
        workspace: Path,
        config: ExpeditionConfig,
    ) -> None:
        """Retry prompt contains the prior rejection reason as context."""
        client = FakeLLMClient(
            responses=[
                "REJECTED — missing gemstone lore",
                "VERIFIED — acceptable for draft",
            ]
        )
        orch = BuildOrchestrator(
            workspace_root=workspace,
            config=config,
            llm_client=client,
        )
        mission = Mission(
            mission_id="m-v3",
            agent="compiler",
            mission_type="compile_article",
            inputs={},
            acceptance_criteria=["Gemstone lore documented"],
            created_by="captain",
        )
        orch._verify_mission(mission)

        # The second call should include the rejection as assistant message
        # and a reconsideration prompt as user message
        second_call = client.calls[1]
        messages = second_call["messages"]
        # Multi-turn: user, assistant (rejection), user (reconsider)
        assert len(messages) >= 3
        assert messages[1]["role"] == "assistant"
        assert "REJECTED" in messages[1]["content"]
        assert messages[2]["role"] == "user"
        assert "Reconsider" in messages[2]["content"]

    def test_all_retries_exhausted_returns_false(
        self,
        workspace: Path,
        config: ExpeditionConfig,
    ) -> None:
        """After max retries, all rejected → returns False."""
        client = FakeLLMClient(
            responses=["REJECTED — fundamentally inadequate"] * 5
        )
        orch = BuildOrchestrator(
            workspace_root=workspace,
            config=config,
            llm_client=client,
        )
        mission = Mission(
            mission_id="m-v4",
            agent="compiler",
            mission_type="compile_article",
            inputs={},
            acceptance_criteria=["Article compiled"],
            created_by="captain",
        )
        assert orch._verify_mission(mission) is False
        # 3 calls: initial + 2 retries (MAX_VERIFY_ATTEMPTS=3)
        assert len(client.calls) == 3

    def test_rejection_reason_stored_on_mission(
        self,
        workspace: Path,
        config: ExpeditionConfig,
    ) -> None:
        """Final rejection reason is stored for debugging."""
        client = FakeLLMClient(
            responses=["REJECTED — totally off topic"] * 5
        )
        orch = BuildOrchestrator(
            workspace_root=workspace,
            config=config,
            llm_client=client,
        )
        mission = Mission(
            mission_id="m-v5",
            agent="compiler",
            mission_type="compile_article",
            inputs={},
            acceptance_criteria=["On topic"],
            created_by="captain",
        )
        orch._verify_mission(mission)
        assert mission.last_rejection_reason
        assert "off topic" in mission.last_rejection_reason.lower()

    def test_rejection_logged_to_structured_log(
        self,
        workspace: Path,
        config: ExpeditionConfig,
    ) -> None:
        """Full verification conversation is logged on final rejection."""
        import json

        client = FakeLLMClient(
            responses=["REJECTED — missing key elements"] * 5
        )
        orch = BuildOrchestrator(
            workspace_root=workspace,
            config=config,
            llm_client=client,
        )
        mission = Mission(
            mission_id="m-v6",
            agent="compiler",
            mission_type="compile_article",
            inputs={},
            acceptance_criteria=["Key elements present"],
            created_by="captain",
        )
        orch._verify_mission(mission)

        # Check captain's structured log for the verification event
        log_file = workspace / ".assistonauts" / "logs" / "captain.jsonl"
        assert log_file.exists()
        entries = [
            json.loads(line)
            for line in log_file.read_text().splitlines()
            if line.strip()
        ]
        rejection_entries = [
            e for e in entries if e.get("event") == "verification_rejected"
        ]
        assert len(rejection_entries) == 1
        entry = rejection_entries[0]
        assert entry["mission_id"] == "m-v6"
        assert entry["attempts"] == 3
        assert "conversation" in entry
        # Conversation has 5 messages: user, assistant, user, assistant, user
        assert len(entry["conversation"]) == 5
        assert entry["conversation"][0]["role"] == "user"
        assert entry["conversation"][1]["role"] == "assistant"

    def test_retry_success_logged_to_structured_log(
        self,
        workspace: Path,
        config: ExpeditionConfig,
    ) -> None:
        """Successful retry is logged with full conversation."""
        import json

        client = FakeLLMClient(
            responses=[
                "REJECTED — needs more detail",
                "VERIFIED — acceptable on reconsideration",
            ]
        )
        orch = BuildOrchestrator(
            workspace_root=workspace,
            config=config,
            llm_client=client,
        )
        mission = Mission(
            mission_id="m-v7",
            agent="compiler",
            mission_type="compile_article",
            inputs={},
            acceptance_criteria=["Detailed content"],
            created_by="captain",
        )
        orch._verify_mission(mission)

        log_file = workspace / ".assistonauts" / "logs" / "captain.jsonl"
        entries = [
            json.loads(line)
            for line in log_file.read_text().splitlines()
            if line.strip()
        ]
        retry_entries = [
            e for e in entries if e.get("event") == "verification_retried"
        ]
        assert len(retry_entries) == 1
        assert retry_entries[0]["mission_id"] == "m-v7"
        assert retry_entries[0]["attempts"] == 2
