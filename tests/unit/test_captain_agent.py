"""Tests for the Captain agent."""

from pathlib import Path

import pytest

from assistonauts.agents.base import OwnershipError
from assistonauts.agents.captain import CaptainAgent, CaptainResult, parse_plan_response
from tests.helpers import FakeLLMClient


@pytest.fixture()
def workspace(tmp_path: Path) -> Path:
    """Create a minimal workspace for Captain testing."""
    dirs = [
        "raw/articles",
        "wiki/concept",
        "wiki/entity",
        "wiki/explorations",
        "index",
        "audits",
        "expeditions",
        "station-logs",
        ".assistonauts/logs",
        ".assistonauts/plans",
    ]
    for d in dirs:
        (tmp_path / d).mkdir(parents=True)
    return tmp_path


@pytest.fixture()
def captain(workspace: Path) -> CaptainAgent:
    """Create a Captain agent with fake LLM client."""
    plan_response = (
        "Based on the sources, I propose the following plan:\n"
        "```yaml\n"
        "missions:\n"
        "  - id: mission-001\n"
        "    agent: scout\n"
        "    type: ingest_sources\n"
        "    inputs:\n"
        "      paths:\n"
        "        - raw/articles/test.md\n"
        "    acceptance_criteria:\n"
        "      - Sources ingested\n"
        "    priority: high\n"
        "  - id: mission-002\n"
        "    agent: compiler\n"
        "    type: compile_article\n"
        "    inputs:\n"
        "      sources:\n"
        "        - raw/articles/test.md\n"
        "    acceptance_criteria:\n"
        "      - Article written\n"
        "      - Summary generated\n"
        "    priority: normal\n"
        "    depends_on:\n"
        "      - mission-001\n"
        "```\n"
    )
    client = FakeLLMClient(responses=[plan_response])
    return CaptainAgent(
        llm_client=client,
        workspace_root=workspace,
    )


# --- Ownership boundaries ---


class TestCaptainOwnership:
    def test_owns_expeditions(self, captain: CaptainAgent) -> None:
        ws = captain.workspace_root
        captain.write_file(ws / "expeditions" / "test.yaml", "data")
        assert (ws / "expeditions" / "test.yaml").exists()

    def test_owns_station_logs(self, captain: CaptainAgent) -> None:
        ws = captain.workspace_root
        captain.write_file(
            ws / "station-logs" / "log.md",
            "log data",
        )
        assert (ws / "station-logs" / "log.md").exists()

    def test_cannot_write_wiki(self, captain: CaptainAgent) -> None:
        ws = captain.workspace_root
        with pytest.raises(OwnershipError):
            captain.write_file(
                ws / "wiki" / "concept" / "test.md",
                "bad",
            )

    def test_cannot_write_raw(self, captain: CaptainAgent) -> None:
        ws = captain.workspace_root
        with pytest.raises(OwnershipError):
            captain.write_file(
                ws / "raw" / "articles" / "test.md",
                "bad",
            )

    def test_can_read_everything(self, captain: CaptainAgent) -> None:
        ws = captain.workspace_root
        # Write a file in wiki and read it
        (ws / "wiki" / "concept" / "test.md").write_text("article")
        content = captain.read_file(
            ws / "wiki" / "concept" / "test.md",
        )
        assert content == "article"

    def test_can_read_raw(self, captain: CaptainAgent) -> None:
        ws = captain.workspace_root
        (ws / "raw" / "articles" / "test.md").write_text("source")
        content = captain.read_file(
            ws / "raw" / "articles" / "test.md",
        )
        assert content == "source"


# --- System prompt ---


class TestCaptainSystemPrompt:
    def test_system_prompt_set(self, captain: CaptainAgent) -> None:
        assert "Captain" in captain.system_prompt
        assert "expedition" in captain.system_prompt.lower()

    def test_role_is_captain(self, captain: CaptainAgent) -> None:
        assert captain.role == "captain"


# --- Planning mode ---


class TestCaptainPlanMode:
    def test_plan_returns_missions(self, captain: CaptainAgent) -> None:
        result = captain.plan(
            source_descriptions=["A paper about FFT analysis"],
            expedition_scope="ML research",
        )
        assert result.success
        assert len(result.missions) > 0

    def test_plan_creates_missions_from_yaml(
        self,
        captain: CaptainAgent,
    ) -> None:
        result = captain.plan(
            source_descriptions=["source A"],
            expedition_scope="test scope",
        )
        assert result.missions[0].mission_id == "mission-001"
        assert result.missions[0].agent == "scout"
        assert result.missions[0].priority == "high"

    def test_plan_captures_dependencies(
        self,
        captain: CaptainAgent,
    ) -> None:
        result = captain.plan(
            source_descriptions=["source A"],
            expedition_scope="test scope",
        )
        # mission-002 depends on mission-001
        assert len(result.dependencies) > 0
        assert ("mission-001", "mission-002") in result.dependencies

    def test_plan_makes_llm_call(
        self,
        captain: CaptainAgent,
    ) -> None:
        captain.plan(
            source_descriptions=["test"],
            expedition_scope="test",
        )
        assert len(captain.llm_client.calls) == 1

    def test_plan_bad_yaml_returns_empty(
        self,
        workspace: Path,
    ) -> None:
        client = FakeLLMClient(
            responses=["This is not valid YAML at all {{{}}}"],
        )
        cap = CaptainAgent(
            llm_client=client,
            workspace_root=workspace,
        )
        result = cap.plan(
            source_descriptions=["test"],
            expedition_scope="test",
        )
        assert result.success
        assert len(result.missions) == 0


# --- Run task (directive routing) ---


class TestCaptainRunTask:
    def test_run_task_plan_directive(
        self,
        captain: CaptainAgent,
    ) -> None:
        result = captain.run_task(
            {
                "directive": "plan",
                "expedition_scope": "ML research",
                "source_descriptions": "paper about FFT",
            }
        )
        assert result.success

    def test_run_task_status_directive(
        self,
        captain: CaptainAgent,
    ) -> None:
        result = captain.run_task({"directive": "status"})
        assert result.success

    def test_run_task_unknown_directive(
        self,
        captain: CaptainAgent,
    ) -> None:
        result = captain.run_task({"directive": "unknown"})
        assert not result.success


# --- CaptainResult ---


class TestCaptainResult:
    def test_result_fields(self) -> None:
        r = CaptainResult(
            success=True,
            output_path=None,
            output_paths=[],
            missions=[],
            dependencies=[],
        )
        assert r.success
        assert r.missions == []
        assert r.dependencies == []


# --- parse_plan_response ---


class TestParsePlanResponse:
    def test_parses_clean_yaml(self) -> None:
        response = (
            "```yaml\n"
            "missions:\n"
            "  - id: m-001\n"
            "    agent: scout\n"
            "    type: ingest\n"
            "    inputs: {}\n"
            "    acceptance_criteria: []\n"
            "    priority: normal\n"
            "```\n"
        )
        missions, _deps = parse_plan_response(response)
        assert len(missions) == 1
        assert missions[0].mission_id == "m-001"

    def test_parses_yaml_with_surrounding_text(self) -> None:
        """LLM response with explanation before/after YAML block."""
        response = (
            "Here's my mission plan for the ML expedition:\n\n"
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
            "```\n\n"
            "This plan ingests all sources first, then compiles.\n"
        )
        missions, _deps = parse_plan_response(response)
        assert len(missions) == 1
        assert missions[0].agent == "scout"

    def test_returns_empty_on_unparseable(self) -> None:
        missions, _deps = parse_plan_response("Just some text, no YAML.")
        assert missions == []
        assert _deps == []

    def test_returns_empty_on_no_missions_key(self) -> None:
        response = "```yaml\nplan:\n  phases: [discovery]\n```\n"
        missions, _deps = parse_plan_response(response)
        assert missions == []

    def test_skips_malformed_entries(self) -> None:
        """Entries missing id or agent are skipped."""
        response = (
            "```yaml\n"
            "missions:\n"
            "  - id: m-001\n"
            "    agent: scout\n"
            "    type: ingest\n"
            "    inputs: {}\n"
            "    acceptance_criteria: []\n"
            "  - type: compile\n"
            "    inputs: {}\n"
            "```\n"
        )
        missions, _ = parse_plan_response(response)
        assert len(missions) == 1  # second entry skipped

    def test_captures_dependencies(self) -> None:
        response = (
            "```yaml\n"
            "missions:\n"
            "  - id: m-001\n"
            "    agent: scout\n"
            "    type: ingest\n"
            "    inputs: {}\n"
            "    acceptance_criteria: []\n"
            "  - id: m-002\n"
            "    agent: compiler\n"
            "    type: compile\n"
            "    inputs: {}\n"
            "    acceptance_criteria: []\n"
            "    depends_on:\n"
            "      - m-001\n"
            "```\n"
        )
        missions, deps = parse_plan_response(response)
        assert len(missions) == 2
        assert ("m-001", "m-002") in deps
