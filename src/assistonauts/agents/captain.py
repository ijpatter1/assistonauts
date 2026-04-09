"""Captain agent — expedition orchestration and mission planning.

The Captain leads the expedition: decomposes objectives into missions,
sequences tasks with dependency ordering, and tracks progress. Uses a
frontier model for high-judgment planning decisions.

Two operational modes:
- Planning mode: expedition decomposition into missions
- Operations mode: routine triage during stationed phase

Owns: expeditions/, station-logs/
Can read: everything
Does NOT: write wiki articles, process raw sources, manage search index
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from assistonauts.agents.base import Agent, LLMClientProtocol
from assistonauts.missions.models import Mission

_CAPTAIN_SYSTEM_PROMPT = """\
You are Captain, the expedition orchestrator for the Assistonauts framework.
Your job is to decompose expedition objectives into sequenced missions,
assign them to the appropriate agents, and track execution progress.

You make strategic decisions: what work needs to happen, in what order,
and which agent should do it. You delegate editorial decisions (article
types, titles, source groupings) to the Compiler's plan mode.

You have full visibility into the knowledge base state: manifests, indexes,
agent statuses, and mission history. You use this to make informed planning
and triage decisions.

Guidelines:
- Sequence missions with correct dependencies: foundational concepts first
- Batch Curator work until compilation is complete (not incremental)
- Track token budget and scale agent instances within configured limits
- Surface items that need human review via the review queue
- Produce structured output that the mission runner can execute

When asked to create a mission plan, output YAML in this format:
```yaml
missions:
  - id: mission-NNN
    agent: scout|compiler|curator|explorer
    type: ingest_sources|compile_article|cross_reference|...
    inputs:
      key: value
    acceptance_criteria:
      - "Criterion 1"
    priority: critical|high|normal|low
    depends_on:  # optional
      - mission-NNN
```
"""


@dataclass
class CaptainResult:
    """Result from a Captain operation."""

    success: bool
    output_path: Path | None = None
    output_paths: list[Path] = field(default_factory=list)
    missions: list[Mission] = field(default_factory=list)
    dependencies: list[tuple[str, str]] = field(default_factory=list)
    status_summary: str = ""


class CaptainAgent(Agent):
    """Captain agent for expedition orchestration."""

    def __init__(
        self,
        llm_client: LLMClientProtocol,
        workspace_root: Path,
    ) -> None:
        self.workspace_root = workspace_root
        super().__init__(
            role="captain",
            system_prompt=_CAPTAIN_SYSTEM_PROMPT,
            llm_client=llm_client,
            owned_dirs=[
                workspace_root / "expeditions",
                workspace_root / "station-logs",
            ],
            readable_dirs=[
                workspace_root / "raw",
                workspace_root / "wiki",
                workspace_root / "index",
                workspace_root / "audits",
                workspace_root / ".assistonauts",
            ],
        )
        self._setup_persistent_logger(workspace_root)

    def run_task(self, task: dict[str, str]) -> CaptainResult:
        """Route a human directive to the appropriate handler."""
        directive = task.get("directive", "")

        if directive == "plan":
            return self.plan(
                source_descriptions=task.get(
                    "source_descriptions",
                    "",
                ).split("\n"),
                expedition_scope=task.get("expedition_scope", ""),
            )
        elif directive == "status":
            return CaptainResult(
                success=True,
                status_summary="Status check — not yet implemented",
            )
        else:
            return CaptainResult(
                success=False,
                status_summary=f"Unknown directive: {directive}",
            )

    def plan(
        self,
        source_descriptions: list[str],
        expedition_scope: str,
    ) -> CaptainResult:
        """Planning mode: decompose sources into missions.

        The Captain analyzes source descriptions and expedition scope to
        produce a sequenced mission plan. Editorial decisions (article
        types, groupings) are deferred to Compiler plan mode.
        """
        sources_text = "\n".join(f"- {s}" for s in source_descriptions if s.strip())
        prompt = (
            f"Expedition scope: {expedition_scope}\n\n"
            f"Available sources:\n{sources_text}\n\n"
            "Create a mission plan to build this knowledge base. "
            "Sequence missions with correct dependencies."
        )

        response = self.call_llm([{"role": "user", "content": prompt}])
        missions, dependencies = parse_plan_response(response)

        return CaptainResult(
            success=True,
            missions=missions,
            dependencies=dependencies,
        )


def parse_plan_response(
    response: str,
) -> tuple[list[Mission], list[tuple[str, str]]]:
    """Parse Captain's YAML plan response into Mission objects.

    Skips malformed mission entries (missing id or agent).
    """
    # Strip markdown code fences
    cleaned = re.sub(r"```ya?ml?\n?", "", response)
    cleaned = re.sub(r"```\n?", "", cleaned)

    try:
        data = yaml.safe_load(cleaned)
    except yaml.YAMLError:
        return [], []

    if not isinstance(data, dict) or "missions" not in data:
        return [], []

    missions: list[Mission] = []
    dependencies: list[tuple[str, str]] = []

    for md in data["missions"]:
        if not isinstance(md, dict):
            continue

        mission_id = str(md.get("id", "")).strip()
        agent = str(md.get("agent", "")).strip()
        if not mission_id or not agent:
            continue  # skip malformed entries

        mission = Mission(
            mission_id=mission_id,
            agent=agent,
            mission_type=str(md.get("type", "")),
            inputs=md.get("inputs", {}),
            acceptance_criteria=md.get("acceptance_criteria", []),
            created_by="captain",
            priority=str(md.get("priority", "normal")),
        )
        missions.append(mission)

        # Capture dependencies
        for dep_id in md.get("depends_on", []):
            dependencies.append((str(dep_id), mission.mission_id))

    return missions, dependencies
