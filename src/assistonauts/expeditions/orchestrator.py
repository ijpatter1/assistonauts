"""Build phase orchestrator with named iteration phases.

Implements the iterative planning model from the spec:
- Discovery: Scout ingests all sources, Compiler compiles first batch
- Structuring: Captain reads summaries, identifies foundational concepts,
  sequences remaining compilations with dependency ordering
- Refinement: Curator batch cross-referencing, Inspector hook (Phase 6)

The Captain's observe step is an LLM call that reads summaries and
makes replanning decisions. Iteration count is variable.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path

from assistonauts.agents.base import LLMClientProtocol
from assistonauts.agents.captain import CaptainAgent, _parse_plan_response
from assistonauts.missions.dependencies import (
    DependencyGraph,
    build_graph_from_plan,
)
from assistonauts.missions.models import Mission
from assistonauts.models.config import ExpeditionConfig


class IterationPhase(Enum):
    """Named iteration phases in the build phase."""

    DISCOVERY = "discovery"
    STRUCTURING = "structuring"
    REFINEMENT = "refinement"


@dataclass
class BuildIteration:
    """Result of a single build phase iteration."""

    phase: IterationPhase
    missions_planned: int = 0
    missions_completed: int = 0
    missions_failed: int = 0
    missions: list[Mission] = field(default_factory=list)
    graph: DependencyGraph | None = None

    def is_complete(self) -> bool:
        return self.missions_completed + self.missions_failed >= self.missions_planned


@dataclass
class BuildPhaseResult:
    """Result of the full build phase."""

    iterations: list[BuildIteration] = field(default_factory=list)
    total_missions: int = 0
    total_completed: int = 0
    total_failed: int = 0


class BuildOrchestrator:
    """Orchestrates the build phase with named iterations.

    Uses the Captain agent for planning decisions. Each iteration
    phase has a specific goal and involves different agents.
    """

    def __init__(
        self,
        workspace_root: Path,
        config: ExpeditionConfig,
        llm_client: LLMClientProtocol,
    ) -> None:
        self.workspace_root = workspace_root
        self.config = config
        self.captain = CaptainAgent(
            llm_client=llm_client,
            workspace_root=workspace_root,
        )
        self._iterations: list[BuildIteration] = []

    @staticmethod
    def iteration_sequence() -> list[IterationPhase]:
        """Return the standard iteration phase ordering."""
        return [
            IterationPhase.DISCOVERY,
            IterationPhase.STRUCTURING,
            IterationPhase.REFINEMENT,
        ]

    def plan_iteration(
        self,
        phase: IterationPhase,
    ) -> BuildIteration:
        """Plan missions for a specific iteration phase.

        The Captain's observe step is an LLM call that reads the
        expedition state and produces missions appropriate for the phase.
        """
        prompt = self._build_prompt(phase)
        response = self.captain.call_llm(
            [{"role": "user", "content": prompt}],
        )

        missions, dependencies = _parse_plan_response(response)
        graph = build_graph_from_plan(missions, dependencies)

        iteration = BuildIteration(
            phase=phase,
            missions_planned=len(missions),
            missions=missions,
            graph=graph,
        )
        self._iterations.append(iteration)
        return iteration

    def _build_prompt(self, phase: IterationPhase) -> str:
        """Build a phase-specific prompt for the Captain."""
        scope = self.config.scope
        scope_text = (
            f"Expedition: {self.config.name}\n"
            f"Scope: {scope.description}\n"
            f"Keywords: {', '.join(scope.keywords)}\n"
        )

        if phase == IterationPhase.DISCOVERY:
            return (
                f"{scope_text}\n"
                "ITERATION PHASE: Discovery\n\n"
                "This is the first iteration. Plan Scout missions "
                "to ingest all configured sources, and initial "
                "Compiler missions for the first batch. "
                "The Archivist will index articles automatically.\n\n"
                f"Sources: {self._describe_sources()}\n\n"
                "Create a mission plan with correct dependencies. "
                "Scout missions should run first, then Compiler."
            )

        elif phase == IterationPhase.STRUCTURING:
            return (
                f"{scope_text}\n"
                "ITERATION PHASE: Structuring\n\n"
                "Discovery is complete. Review the compiled articles "
                "and their summaries. Identify foundational concepts "
                "that other articles will reference. Sequence "
                "remaining Compiler missions with correct "
                "dependency ordering — foundational concepts first.\n\n"
                "Identify structural needs: are there concepts "
                "that need dedicated entity pages or category "
                "articles?\n\n"
                "Create a mission plan for the remaining work."
            )

        else:  # REFINEMENT
            return (
                f"{scope_text}\n"
                "ITERATION PHASE: Refinement\n\n"
                "All sources are compiled and indexed. Plan:\n"
                "1. Curator cross-referencing pass over all articles "
                "(batched — not incremental, since the full corpus "
                "is now available)\n"
                "2. Inspector sweep (placeholder — Phase 6)\n\n"
                "Create missions for the refinement pass."
            )

    def _describe_sources(self) -> str:
        """Describe configured sources for the prompt."""
        parts = []
        for ls in self.config.sources.local:
            parts.append(f"Local: {ls.path} ({ls.pattern})")
        return "; ".join(parts) if parts else "No sources configured"
