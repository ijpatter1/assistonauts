"""Tests for the build phase orchestrator with named iterations."""

import json
from pathlib import Path

import pytest

from assistonauts.expeditions.orchestrator import (
    BuildIteration,
    BuildOrchestrator,
    BuildPhaseResult,
    IterationPhase,
)
from assistonauts.missions.models import Mission, MissionStatus
from assistonauts.models.config import ExpeditionConfig
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
                "description": "ML research",
                "keywords": ["ML", "BTC"],
            },
            "sources": {
                "local": [{"path": "/tmp/papers", "pattern": "*.pdf"}],
            },
        }
    )


# --- IterationPhase enum ---


class TestIterationPhase:
    def test_all_phases(self) -> None:
        assert IterationPhase.DISCOVERY.value == "discovery"
        assert IterationPhase.STRUCTURING.value == "structuring"
        assert IterationPhase.REFINEMENT.value == "refinement"


# --- BuildIteration ---


class TestBuildIteration:
    def test_creation(self) -> None:
        it = BuildIteration(
            phase=IterationPhase.DISCOVERY,
            missions_planned=5,
            missions_completed=3,
            missions_failed=1,
        )
        assert it.phase == IterationPhase.DISCOVERY
        assert it.missions_planned == 5

    def test_is_complete(self) -> None:
        it = BuildIteration(
            phase=IterationPhase.DISCOVERY,
            missions_planned=3,
            missions_completed=3,
            missions_failed=0,
        )
        assert it.is_complete()

    def test_not_complete(self) -> None:
        it = BuildIteration(
            phase=IterationPhase.DISCOVERY,
            missions_planned=5,
            missions_completed=3,
            missions_failed=0,
        )
        assert not it.is_complete()


# --- BuildOrchestrator ---


class TestBuildOrchestrator:
    def test_plan_discovery(
        self,
        workspace: Path,
        config: ExpeditionConfig,
    ) -> None:
        plan_response = (
            "```yaml\n"
            "missions:\n"
            "  - id: m-scout-001\n"
            "    agent: scout\n"
            "    type: ingest_sources\n"
            "    inputs:\n"
            "      paths:\n"
            "        - /tmp/papers/a.pdf\n"
            "    acceptance_criteria:\n"
            "      - Sources ingested\n"
            "    priority: high\n"
            "  - id: m-compile-001\n"
            "    agent: compiler\n"
            "    type: compile_batch\n"
            "    inputs:\n"
            "      sources:\n"
            "        - raw/articles/a.md\n"
            "    acceptance_criteria:\n"
            "      - Articles compiled\n"
            "    priority: normal\n"
            "    depends_on:\n"
            "      - m-scout-001\n"
            "```\n"
        )
        client = FakeLLMClient(responses=[plan_response])
        orch = BuildOrchestrator(
            workspace_root=workspace,
            config=config,
            llm_client=client,
        )

        iteration = orch.plan_iteration(IterationPhase.DISCOVERY)
        assert iteration.phase == IterationPhase.DISCOVERY
        assert iteration.missions_planned == 2

    def test_plan_structuring(
        self,
        workspace: Path,
        config: ExpeditionConfig,
    ) -> None:
        # Structuring reads compiled article summaries
        observe_response = (
            "```yaml\n"
            "missions:\n"
            "  - id: m-compile-002\n"
            "    agent: compiler\n"
            "    type: compile_article\n"
            "    inputs:\n"
            "      sources:\n"
            "        - raw/articles/b.md\n"
            "    acceptance_criteria:\n"
            "      - Article compiled\n"
            "    priority: normal\n"
            "    depends_on:\n"
            "      - m-compile-001\n"
            "```\n"
        )
        client = FakeLLMClient(responses=[observe_response])
        orch = BuildOrchestrator(
            workspace_root=workspace,
            config=config,
            llm_client=client,
        )

        iteration = orch.plan_iteration(
            IterationPhase.STRUCTURING,
        )
        assert iteration.phase == IterationPhase.STRUCTURING
        assert iteration.missions_planned == 1

    def test_plan_refinement(
        self,
        workspace: Path,
        config: ExpeditionConfig,
    ) -> None:
        refine_response = (
            "```yaml\n"
            "missions:\n"
            "  - id: m-curate-001\n"
            "    agent: curator\n"
            "    type: cross_reference\n"
            "    inputs: {}\n"
            "    acceptance_criteria:\n"
            "      - Cross-references added\n"
            "    priority: normal\n"
            "```\n"
        )
        client = FakeLLMClient(responses=[refine_response])
        orch = BuildOrchestrator(
            workspace_root=workspace,
            config=config,
            llm_client=client,
        )

        iteration = orch.plan_iteration(
            IterationPhase.REFINEMENT,
        )
        assert iteration.phase == IterationPhase.REFINEMENT
        assert iteration.missions_planned == 1

    def test_iteration_sequence(
        self,
        workspace: Path,
        config: ExpeditionConfig,
    ) -> None:
        """Verify the iteration phase ordering."""
        orch = BuildOrchestrator(
            workspace_root=workspace,
            config=config,
            llm_client=FakeLLMClient(responses=["no yaml"]),
        )
        phases = orch.iteration_sequence()
        assert phases == [
            IterationPhase.DISCOVERY,
            IterationPhase.STRUCTURING,
            IterationPhase.REFINEMENT,
        ]

    def test_get_iteration_prompt_varies_by_phase(
        self,
        workspace: Path,
        config: ExpeditionConfig,
    ) -> None:
        client = FakeLLMClient(responses=["no yaml"] * 3)
        orch = BuildOrchestrator(
            workspace_root=workspace,
            config=config,
            llm_client=client,
        )

        orch.plan_iteration(IterationPhase.DISCOVERY)
        orch.plan_iteration(IterationPhase.STRUCTURING)
        orch.plan_iteration(IterationPhase.REFINEMENT)

        prompts = [call["messages"][0]["content"] for call in client.calls]
        # Each phase should produce a different prompt
        assert len(set(prompts)) == 3
        assert "discovery" in prompts[0].lower()
        assert "structuring" in prompts[1].lower()
        assert "refinement" in prompts[2].lower()


# --- Execution tests ---


class TestBuildExecution:
    def test_execute_iteration_saves_to_ledger(
        self,
        workspace: Path,
        config: ExpeditionConfig,
    ) -> None:
        plan_response = (
            "```yaml\n"
            "missions:\n"
            "  - id: m-001\n"
            "    agent: scout\n"
            "    type: ingest_sources\n"
            "    inputs:\n"
            "      paths:\n"
            "        - /tmp/test.md\n"
            "    acceptance_criteria:\n"
            "      - Sources ingested\n"
            "    priority: normal\n"
            "```\n"
        )
        # Scout agent will fail (no real file) but ledger should record it
        client = FakeLLMClient(responses=[plan_response, "scout output"])
        orch = BuildOrchestrator(
            workspace_root=workspace,
            config=config,
            llm_client=client,
        )

        iteration = orch.plan_iteration(IterationPhase.DISCOVERY)
        orch.execute_iteration(iteration)

        # Verify mission was saved to ledger
        saved = orch.ledger.get("m-001")
        assert saved is not None
        assert saved.status in (
            MissionStatus.COMPLETED,
            MissionStatus.FAILED,
        )

    def test_execute_empty_iteration(
        self,
        workspace: Path,
        config: ExpeditionConfig,
    ) -> None:
        client = FakeLLMClient(responses=["no missions"])
        orch = BuildOrchestrator(
            workspace_root=workspace,
            config=config,
            llm_client=client,
        )

        iteration = orch.plan_iteration(IterationPhase.DISCOVERY)
        result = orch.execute_iteration(iteration)
        assert result.missions_planned == 0
        assert result.missions_completed == 0

    def test_run_build_returns_result(
        self,
        workspace: Path,
        config: ExpeditionConfig,
    ) -> None:
        # 3 iterations, each returns empty plan
        client = FakeLLMClient(responses=["no yaml"] * 3)
        orch = BuildOrchestrator(
            workspace_root=workspace,
            config=config,
            llm_client=client,
        )

        result = orch.run_build()
        assert isinstance(result, BuildPhaseResult)
        assert len(result.iterations) == 3
        assert result.iterations[0].phase == IterationPhase.DISCOVERY
        assert result.iterations[1].phase == IterationPhase.STRUCTURING
        assert result.iterations[2].phase == IterationPhase.REFINEMENT

    def test_budget_halt_stops_execution(
        self,
        workspace: Path,
        config: ExpeditionConfig,
    ) -> None:
        plan_response = (
            "```yaml\n"
            "missions:\n"
            "  - id: m-001\n"
            "    agent: scout\n"
            "    type: ingest\n"
            "    inputs: {}\n"
            "    acceptance_criteria: []\n"
            "    priority: normal\n"
            "  - id: m-002\n"
            "    agent: scout\n"
            "    type: ingest\n"
            "    inputs: {}\n"
            "    acceptance_criteria: []\n"
            "    priority: normal\n"
            "```\n"
        )
        client = FakeLLMClient(responses=[plan_response])
        orch = BuildOrchestrator(
            workspace_root=workspace,
            config=config,
            llm_client=client,
        )

        # Exhaust the budget before execution
        orch.budget.tracker.record(
            agent="test",
            expedition="test",
            tokens=200_000,
        )

        iteration = orch.plan_iteration(IterationPhase.DISCOVERY)
        orch.execute_iteration(iteration)

        # Neither mission should have completed (budget halt)
        assert iteration.missions_completed == 0

    def test_structuring_prompt_includes_summaries(
        self,
        workspace: Path,
        config: ExpeditionConfig,
    ) -> None:
        # Create a summary file
        summary_dir = workspace / "wiki" / "concept"
        summary_dir.mkdir(parents=True, exist_ok=True)
        (summary_dir / "test.summary.json").write_text(
            json.dumps(
                {
                    "title": "Test Article",
                    "summary": "An article about testing.",
                }
            ),
        )

        client = FakeLLMClient(responses=["no yaml"])
        orch = BuildOrchestrator(
            workspace_root=workspace,
            config=config,
            llm_client=client,
        )

        orch.plan_iteration(IterationPhase.STRUCTURING)
        prompt = client.calls[0]["messages"][0]["content"]
        assert "Test Article" in prompt
        assert "An article about testing" in prompt

    def test_plan_yaml_written(
        self,
        workspace: Path,
        config: ExpeditionConfig,
    ) -> None:
        client = FakeLLMClient(responses=["no yaml"])
        orch = BuildOrchestrator(
            workspace_root=workspace,
            config=config,
            llm_client=client,
        )

        orch.plan_iteration(IterationPhase.DISCOVERY)

        plan_path = workspace / "expeditions" / "test-exp" / "plan.yaml"
        assert plan_path.exists()
        import yaml

        data = yaml.safe_load(plan_path.read_text())
        assert data["expedition"] == "test-exp"
        assert len(data["iterations"]) == 1
        assert data["iterations"][0]["phase"] == "discovery"

    def test_corrupted_plan_yaml_recovery(
        self,
        workspace: Path,
        config: ExpeditionConfig,
    ) -> None:
        """Corrupted plan.yaml is overwritten, not crash."""
        client = FakeLLMClient(responses=["no yaml"])
        orch = BuildOrchestrator(
            workspace_root=workspace,
            config=config,
            llm_client=client,
        )

        # Write corrupted plan.yaml
        plan_path = workspace / "expeditions" / "test-exp" / "plan.yaml"
        plan_path.parent.mkdir(parents=True, exist_ok=True)
        plan_path.write_text("{{{invalid yaml")

        # Should not crash — overwrites with fresh data
        orch.plan_iteration(IterationPhase.DISCOVERY)
        import yaml

        data = yaml.safe_load(plan_path.read_text())
        assert data["expedition"] == "test-exp"

    def test_build_report_written(
        self,
        workspace: Path,
        config: ExpeditionConfig,
    ) -> None:
        client = FakeLLMClient(responses=["no yaml"] * 3)
        orch = BuildOrchestrator(
            workspace_root=workspace,
            config=config,
            llm_client=client,
        )

        orch.run_build()

        report_path = workspace / "expeditions" / "test-exp" / "build-report.md"
        assert report_path.exists()
        content = report_path.read_text()
        assert "test-exp" in content
        assert "Discovery" in content
        assert "Structuring" in content
        assert "Refinement" in content

    def test_mission_to_params_scout(
        self,
        workspace: Path,
        config: ExpeditionConfig,
    ) -> None:
        from assistonauts.expeditions.orchestrator import (
            BuildOrchestrator,
        )
        from assistonauts.missions.models import Mission

        m = Mission(
            mission_id="test",
            agent="scout",
            mission_type="ingest",
            inputs={"paths": ["/tmp/a.pdf"]},
            acceptance_criteria=[],
            created_by="captain",
        )
        params = BuildOrchestrator._mission_to_params(m)
        assert params["source_path"] == "/tmp/a.pdf"

    def test_mission_to_params_compiler_multi(
        self,
        workspace: Path,
        config: ExpeditionConfig,
    ) -> None:
        from assistonauts.missions.models import Mission

        m = Mission(
            mission_id="test",
            agent="compiler",
            mission_type="compile",
            inputs={
                "sources": ["a.md", "b.md"],
                "title": "Test",
            },
            acceptance_criteria=[],
            created_by="captain",
        )
        params = BuildOrchestrator._mission_to_params(m)
        assert params["source_paths"] == "a.md,b.md"
        assert params["title"] == "Test"

    def test_mission_to_params_curator(
        self,
        workspace: Path,
        config: ExpeditionConfig,
    ) -> None:
        from assistonauts.missions.models import Mission

        m = Mission(
            mission_id="test",
            agent="curator",
            mission_type="cross_reference",
            inputs={"article_path": "wiki/concept/test.md"},
            acceptance_criteria=[],
            created_by="captain",
        )
        params = BuildOrchestrator._mission_to_params(m)
        assert params["article_path"] == "wiki/concept/test.md"

    def test_mission_to_params_explorer(
        self,
        workspace: Path,
        config: ExpeditionConfig,
    ) -> None:
        from assistonauts.missions.models import Mission

        m = Mission(
            mission_id="test",
            agent="explorer",
            mission_type="query",
            inputs={"query": "What is ML?"},
            acceptance_criteria=[],
            created_by="captain",
        )
        params = BuildOrchestrator._mission_to_params(m)
        assert params["query"] == "What is ML?"

    def test_mission_to_params_captain(
        self,
        workspace: Path,
        config: ExpeditionConfig,
    ) -> None:
        from assistonauts.missions.models import Mission

        m = Mission(
            mission_id="test",
            agent="captain",
            mission_type="plan",
            inputs={"directive": "plan"},
            acceptance_criteria=[],
            created_by="captain",
        )
        params = BuildOrchestrator._mission_to_params(m)
        assert params["directive"] == "plan"

    def test_mission_to_params_scout_multi_path(
        self,
        workspace: Path,
        config: ExpeditionConfig,
    ) -> None:
        from assistonauts.missions.models import Mission

        m = Mission(
            mission_id="test",
            agent="scout",
            mission_type="ingest",
            inputs={"paths": ["/tmp/a.pdf", "/tmp/b.pdf", "/tmp/c.pdf"]},
            acceptance_criteria=[],
            created_by="captain",
        )
        params = BuildOrchestrator._mission_to_params(m)
        assert params["source_path"] == "/tmp/a.pdf,/tmp/b.pdf,/tmp/c.pdf"

    def test_validate_params_missing_source(
        self,
        workspace: Path,
        config: ExpeditionConfig,
    ) -> None:
        from assistonauts.missions.models import Mission

        m = Mission(
            mission_id="test",
            agent="compiler",
            mission_type="compile",
            inputs={},  # missing sources
            acceptance_criteria=[],
            created_by="captain",
        )
        params = BuildOrchestrator._mission_to_params(m)
        with pytest.raises(ValueError, match="compiler requires"):
            BuildOrchestrator._validate_params(m, params)


# --- Two-level completion ---


class TestTwoLevelCompletion:
    def test_verify_mission_approved(
        self,
        workspace: Path,
        config: ExpeditionConfig,
    ) -> None:
        """Captain verification passes when response contains VERIFIED."""
        client = FakeLLMClient(responses=["VERIFIED — all criteria met"])
        orch = BuildOrchestrator(
            workspace_root=workspace,
            config=config,
            llm_client=client,
        )
        mission = Mission(
            mission_id="m-001",
            agent="compiler",
            mission_type="compile",
            inputs={"sources": ["a.md"]},
            acceptance_criteria=["Article compiled", "Frontmatter present"],
            created_by="captain",
        )
        assert orch._verify_mission(mission) is True
        assert len(client.calls) == 1

    def test_verify_mission_rejected(
        self,
        workspace: Path,
        config: ExpeditionConfig,
    ) -> None:
        """Captain verification fails when response says REJECTED."""
        client = FakeLLMClient(responses=["REJECTED — missing sections"])
        orch = BuildOrchestrator(
            workspace_root=workspace,
            config=config,
            llm_client=client,
        )
        mission = Mission(
            mission_id="m-001",
            agent="compiler",
            mission_type="compile",
            inputs={"sources": ["a.md"]},
            acceptance_criteria=["Article compiled"],
            created_by="captain",
        )
        assert orch._verify_mission(mission) is False

    def test_verify_mission_no_criteria_auto_approves(
        self,
        workspace: Path,
        config: ExpeditionConfig,
    ) -> None:
        """No acceptance_criteria skips verification (auto-approve)."""
        client = FakeLLMClient(responses=[])
        orch = BuildOrchestrator(
            workspace_root=workspace,
            config=config,
            llm_client=client,
        )
        mission = Mission(
            mission_id="m-001",
            agent="scout",
            mission_type="ingest",
            inputs={},
            acceptance_criteria=[],
            created_by="captain",
        )
        assert orch._verify_mission(mission) is True
        assert len(client.calls) == 0

    def test_verify_prompt_includes_criteria(
        self,
        workspace: Path,
        config: ExpeditionConfig,
    ) -> None:
        """Verification prompt contains the mission's acceptance criteria."""
        client = FakeLLMClient(responses=["VERIFIED"])
        orch = BuildOrchestrator(
            workspace_root=workspace,
            config=config,
            llm_client=client,
        )
        mission = Mission(
            mission_id="m-test",
            agent="compiler",
            mission_type="compile",
            inputs={},
            acceptance_criteria=["Criterion Alpha", "Criterion Beta"],
            created_by="captain",
        )
        orch._verify_mission(mission)
        prompt = client.calls[0]["messages"][0]["content"]
        assert "Criterion Alpha" in prompt
        assert "Criterion Beta" in prompt
        assert "m-test" in prompt

    def test_completed_mission_has_captain_verification(
        self,
        workspace: Path,
        config: ExpeditionConfig,
    ) -> None:
        """End-to-end: task succeeds, Captain verifies, checklist records it."""
        # Create a real source file for scout to ingest
        source_file = workspace / "test-source.md"
        source_file.write_text("# Test Source\n\nSome content.")
        # Ensure manifest exists
        (workspace / "index" / "manifest.json").write_text("{}")

        plan_response = (
            "```yaml\n"
            "missions:\n"
            "  - id: m-scout-001\n"
            "    agent: scout\n"
            "    type: ingest\n"
            "    inputs:\n"
            "      paths:\n"
            "        - " + str(source_file) + "\n"
            "    acceptance_criteria:\n"
            "      - Source file ingested\n"
            "    priority: normal\n"
            "```\n"
        )
        # Response 0: plan, Response 1: verification (scout text ingest has no LLM call)
        client = FakeLLMClient(
            responses=[plan_response, "VERIFIED — source ingested"],
        )
        orch = BuildOrchestrator(
            workspace_root=workspace,
            config=config,
            llm_client=client,
        )

        iteration = orch.plan_iteration(IterationPhase.DISCOVERY)
        orch.execute_iteration(iteration)

        mission = iteration.missions[0]
        assert mission.status == MissionStatus.COMPLETED
        assert any("verified_by:captain" in item for item in mission.checklist)

    def test_rejected_mission_fails(
        self,
        workspace: Path,
        config: ExpeditionConfig,
    ) -> None:
        """End-to-end: task succeeds but Captain rejects → mission fails."""
        source_file = workspace / "test-source.md"
        source_file.write_text("# Test Source\n\nSome content.")
        (workspace / "index" / "manifest.json").write_text("{}")

        plan_response = (
            "```yaml\n"
            "missions:\n"
            "  - id: m-scout-001\n"
            "    agent: scout\n"
            "    type: ingest\n"
            "    inputs:\n"
            "      paths:\n"
            "        - " + str(source_file) + "\n"
            "    acceptance_criteria:\n"
            "      - Source file ingested\n"
            "    priority: normal\n"
            "```\n"
        )
        client = FakeLLMClient(
            responses=[plan_response, "REJECTED — criteria not met"],
        )
        orch = BuildOrchestrator(
            workspace_root=workspace,
            config=config,
            llm_client=client,
        )

        iteration = orch.plan_iteration(IterationPhase.DISCOVERY)
        orch.execute_iteration(iteration)

        mission = iteration.missions[0]
        assert mission.status == MissionStatus.FAILED
        assert mission.failure is not None
        assert "rejected" in mission.failure.error_message.lower()
