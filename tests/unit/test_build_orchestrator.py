"""Tests for the build phase orchestrator with named iterations."""

from pathlib import Path

import pytest

from assistonauts.expeditions.orchestrator import (
    BuildIteration,
    BuildOrchestrator,
    IterationPhase,
)
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
