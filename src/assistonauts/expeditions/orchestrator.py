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

import json
import logging
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path

import yaml

from assistonauts.agents.base import LLMClientProtocol
from assistonauts.agents.captain import CaptainAgent, parse_plan_response
from assistonauts.expeditions.budget import BudgetEnforcer
from assistonauts.expeditions.scaling import ScalingManager
from assistonauts.missions.dependencies import (
    DependencyGraph,
    build_graph_from_plan,
)
from assistonauts.missions.models import Mission, MissionStatus
from assistonauts.models.config import ExpeditionConfig
from assistonauts.tasks.runner import Task, TaskRunner
from assistonauts.tools.captain import MissionLedger

logger = logging.getLogger(__name__)


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
        self.llm_client = llm_client
        self.captain = CaptainAgent(
            llm_client=llm_client,
            workspace_root=workspace_root,
        )
        exp_dir = workspace_root / "expeditions" / config.name
        exp_dir.mkdir(parents=True, exist_ok=True)
        missions_dir = exp_dir / "missions"
        missions_dir.mkdir(exist_ok=True)

        self.ledger = MissionLedger(
            db_path=exp_dir / "ledger.db",
            yaml_dir=missions_dir,
        )
        self.budget = BudgetEnforcer.from_config(
            config.scaling.budget,
            exp_dir / "budget.db",
        )
        self.scaling = ScalingManager(config.scaling)
        self._tokens_before_task = 0
        self.task_runner = TaskRunner(
            workspace_root=workspace_root,
            tasks_dir=workspace_root / ".assistonauts" / "tasks",
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

        missions, dependencies = parse_plan_response(response)
        if not missions:
            logger.warning(
                "No missions planned for %s iteration — "
                "the LLM response could not be parsed into a valid plan",
                phase.value,
            )
        graph = build_graph_from_plan(dependencies)

        iteration = BuildIteration(
            phase=phase,
            missions_planned=len(missions),
            missions=missions,
            graph=graph,
        )
        self._iterations.append(iteration)

        # Write plan.yaml artifact
        self._write_plan_yaml(phase, missions, dependencies)

        return iteration

    def execute_iteration(
        self,
        iteration: BuildIteration,
        prior_completed: set[str] | None = None,
    ) -> BuildIteration:
        """Execute all missions in an iteration in dependency order.

        Dispatches each ready mission to its agent via the TaskRunner,
        records results in the ledger, checks the budget before each
        mission, and handles failures.

        prior_completed: mission IDs completed in earlier iterations,
        so cross-iteration dependencies resolve correctly.
        """
        if not iteration.missions:
            return iteration

        # Save all missions to ledger
        for m in iteration.missions:
            self.ledger.save(m)

        completed: set[str] = set(prior_completed or set())
        pending = {m.mission_id for m in iteration.missions}
        graph = iteration.graph or DependencyGraph()

        while pending:
            # Check budget before dispatching
            budget_status = self.budget.check()
            if not budget_status.can_proceed:
                logger.warning(
                    "Budget exceeded — halting iteration: %s",
                    budget_status.message,
                )
                break
            if budget_status.is_warning:
                logger.warning("Budget warning: %s", budget_status.message)

            # Find ready missions
            ready = graph.ready_missions(pending, completed)
            if not ready:
                # All remaining missions are blocked
                logger.warning(
                    "No ready missions — %d blocked",
                    len(pending),
                )
                break

            for mid in sorted(ready):
                mission = next(m for m in iteration.missions if m.mission_id == mid)
                self._execute_mission(mission)

                if mission.status == MissionStatus.COMPLETED:
                    completed.add(mid)
                    pending.discard(mid)
                    iteration.missions_completed += 1
                elif mission.status == MissionStatus.FAILED:
                    pending.discard(mid)
                    iteration.missions_failed += 1

        return iteration

    def run_build(self) -> BuildPhaseResult:
        """Run the full build phase: plan and execute all iterations.

        Carries completed mission IDs across iterations so that
        Structuring missions can depend on Discovery output.
        """
        result = BuildPhaseResult()
        all_completed: set[str] = set()

        for phase in self.iteration_sequence():
            iteration = self.plan_iteration(phase)
            iteration = self.execute_iteration(
                iteration,
                prior_completed=all_completed,
            )
            # Carry forward completed missions
            for m in iteration.missions:
                if m.status == MissionStatus.COMPLETED:
                    all_completed.add(m.mission_id)
            result.iterations.append(iteration)
            result.total_missions += iteration.missions_planned
            result.total_completed += iteration.missions_completed
            result.total_failed += iteration.missions_failed

        self._write_build_report(result)
        return result

    def _execute_mission(
        self,
        mission: Mission,
        max_retries: int = 3,
    ) -> None:
        """Execute a single mission via the TaskRunner.

        Retries transient failures up to max_retries times.
        Deterministic failures fail-fast with no retry.
        """
        for attempt in range(max_retries + 1):
            if mission.status == MissionStatus.PENDING:
                mission.start()
                self.ledger.save(mission)

            instance_id = self.scaling.acquire(mission.agent)
            if instance_id is None:
                mission.fail(
                    error_type="transient",
                    error_message=f"No available {mission.agent} instance",
                    retries=attempt,
                )
                self.ledger.save(mission)
                if attempt < max_retries:
                    mission.retry()
                    continue
                return

            try:
                self._snapshot_token_count()
                task = Task(
                    task_id=f"task-{mission.mission_id}-{attempt}",
                    agent=mission.agent,
                    params=self._mission_to_params(mission),
                )
                task_result = self.task_runner.run(
                    task,
                    self.llm_client,
                )

                # Record token usage delta since snapshot
                tokens = self._get_tokens_delta()
                if tokens > 0:
                    self.budget.tracker.record(
                        agent=mission.agent,
                        expedition=self.config.name,
                        tokens=tokens,
                    )

                if task_result.success:
                    mission.complete()
                    self.ledger.save(mission)
                    return

                error_type = task_result.error_type or "deterministic"
                mission.fail(
                    error_type=error_type,
                    error_message=task_result.error_message,
                    retries=attempt,
                )
                self.ledger.save(mission)

                # Deterministic failures: no retry
                if error_type == "deterministic":
                    return
                # Transient failures: retry if attempts remain
                if attempt < max_retries:
                    mission.retry()
                    continue
                return

            except Exception as exc:
                mission.fail(
                    error_type="transient",
                    error_message=str(exc),
                    retries=attempt,
                )
                self.ledger.save(mission)
                if attempt < max_retries:
                    mission.retry()
                    continue
                return
            finally:
                self.scaling.release(mission.agent, instance_id)

    @staticmethod
    def _mission_to_params(mission: Mission) -> dict[str, str]:
        """Convert mission inputs to agent-specific task params.

        Each agent expects different keys:
        - Scout: source_path
        - Compiler: source_path (single) or source_paths (comma-sep)
        - Curator: article_path
        - Explorer: query
        - Captain: directive
        """
        params: dict[str, str] = {}
        inputs = mission.inputs
        agent = mission.agent

        if agent == "scout":
            paths = inputs.get("paths") or inputs.get("sources") or []
            if isinstance(paths, list) and paths:
                params["source_path"] = str(paths[0])
        elif agent == "compiler":
            sources = inputs.get("sources", [])
            if isinstance(sources, list):
                if len(sources) == 1:
                    params["source_path"] = str(sources[0])
                elif len(sources) > 1:
                    params["source_paths"] = ",".join(str(s) for s in sources)
            if isinstance(inputs.get("title"), str):
                params["title"] = inputs["title"]
            if isinstance(inputs.get("article_type"), str):
                params["article_type"] = inputs["article_type"]
        elif agent == "curator":
            path = inputs.get("article_path", "")
            if isinstance(path, str) and path:
                params["article_path"] = path
        elif agent == "explorer":
            query = inputs.get("query", "")
            if isinstance(query, str) and query:
                params["query"] = query
        elif agent == "captain":
            params["directive"] = str(
                inputs.get("directive", "status"),
            )

        return params

    def _snapshot_token_count(self) -> None:
        """Snapshot the current total token usage before a task."""
        self._tokens_before_task = self.budget.tracker.get_daily_total()

    def _get_tokens_delta(self) -> int:
        """Get tokens consumed since the last snapshot.

        Falls back to estimating from the LLM client's call count
        if direct tracking is not available. Uses the StructuredLogger
        on the Captain agent as a proxy — each LLM call logs token
        counts. We read the budget tracker's current total and diff.
        """
        current = self.budget.tracker.get_daily_total()
        delta = current - self._tokens_before_task
        if delta > 0:
            return delta
        # If no delta from tracker (tokens weren't recorded by another
        # path), estimate from the LLM client's calls attribute
        calls = getattr(self.llm_client, "calls", None)
        if isinstance(calls, list) and calls:
            last_call = calls[-1]
            if isinstance(last_call, dict):
                return 1000  # conservative estimate per LLM call
        return 0

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
            summaries = self._load_article_summaries()
            summaries_text = (
                "\n".join(f"- {title}: {summary}" for title, summary in summaries)
                if summaries
                else "(no summaries available yet)"
            )
            return (
                f"{scope_text}\n"
                "ITERATION PHASE: Structuring\n\n"
                "Discovery is complete. Review the compiled articles "
                "and their summaries below. Identify foundational "
                "concepts that other articles will reference. "
                "Sequence remaining Compiler missions with correct "
                "dependency ordering — foundational concepts first.\n\n"
                f"Compiled article summaries:\n{summaries_text}\n\n"
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

    def _write_plan_yaml(
        self,
        phase: IterationPhase,
        missions: list[Mission],
        dependencies: list[tuple[str, str]],
    ) -> None:
        """Write the plan artifact to expeditions/<name>/plan.yaml."""
        exp_dir = self.workspace_root / "expeditions" / self.config.name
        plan_path = exp_dir / "plan.yaml"

        # Append to existing plan or create new
        existing: list[dict[str, object]] = []
        if plan_path.exists():
            try:
                data = yaml.safe_load(plan_path.read_text())
                if isinstance(data, dict):
                    existing = data.get("iterations", [])
            except yaml.YAMLError:
                pass

        iteration_data = {
            "phase": phase.value,
            "missions": [m.mission_id for m in missions],
            "dependencies": [{"from": d[0], "to": d[1]} for d in dependencies],
        }
        existing.append(iteration_data)

        plan_data = {
            "expedition": self.config.name,
            "iterations": existing,
        }
        plan_path.write_text(
            yaml.dump(plan_data, default_flow_style=False),
        )

    def _write_build_report(self, result: BuildPhaseResult) -> None:
        """Write a build report to expeditions/<name>/build-report.md."""
        exp_dir = self.workspace_root / "expeditions" / self.config.name
        report_path = exp_dir / "build-report.md"

        lines = [
            f"# Build Report — {self.config.name}",
            "",
            f"**Scope:** {self.config.scope.description}",
            f"**Total missions:** {result.total_missions}",
            f"**Completed:** {result.total_completed}",
            f"**Failed:** {result.total_failed}",
            "",
            "## Iterations",
            "",
        ]

        for it in result.iterations:
            status = "complete" if it.is_complete() else "partial"
            lines.append(f"### {it.phase.value.title()} ({status})")
            lines.append(
                f"- Planned: {it.missions_planned}, "
                f"Completed: {it.missions_completed}, "
                f"Failed: {it.missions_failed}"
            )
            for m in it.missions:
                lines.append(
                    f"  - [{m.mission_id}] {m.agent}/{m.mission_type}"
                    f" — {m.status.value}"
                )
            lines.append("")

        report_path.write_text("\n".join(lines))

    def _load_article_summaries(self) -> list[tuple[str, str]]:
        """Load compiled article summaries from the wiki directory."""
        summaries: list[tuple[str, str]] = []
        wiki_dir = self.workspace_root / "wiki"
        if not wiki_dir.exists():
            return summaries

        for summary_file in wiki_dir.rglob("*.summary.json"):
            try:
                data = json.loads(summary_file.read_text())
                title = data.get("title", summary_file.stem)
                summary = data.get("summary", "")
                if summary:
                    summaries.append((str(title), str(summary)))
            except (json.JSONDecodeError, OSError):
                continue
        return summaries
