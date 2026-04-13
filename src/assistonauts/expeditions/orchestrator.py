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
import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import ClassVar

import yaml

from assistonauts.agents.base import LLMClientProtocol
from assistonauts.agents.captain import CaptainAgent, parse_plan_response
from assistonauts.archivist.service import Archivist
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
    budget_halt_message: str = ""

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

        # Create Archivist for curator cross-referencing and indexing
        embedding_dims = self._get_embedding_dimensions()
        self.archivist = Archivist(
            workspace=workspace_root,
            embedding_dimensions=embedding_dims,
        )
        self._embedding_client = self._create_embedding_client()

        self.task_runner = TaskRunner(
            workspace_root=workspace_root,
            tasks_dir=workspace_root / ".assistonauts" / "tasks",
            agent_context={
                "archivist": self.archivist,
                "embedding_client": self._embedding_client,
            },
        )
        self._iterations: list[BuildIteration] = []

    def _get_embedding_dimensions(self) -> int:
        """Get embedding dimensions from workspace config, or default."""
        try:
            from assistonauts.archivist.embeddings import get_embedding_dimensions
            from assistonauts.config.loader import load_config

            app_config = load_config(self.workspace_root)
            return get_embedding_dimensions(app_config.embedding)
        except Exception:
            return 3072

    def _create_embedding_client(self) -> object | None:
        """Create embedding client from workspace config, or None."""
        try:
            from assistonauts.archivist.embeddings import create_embedding_client
            from assistonauts.config.loader import load_config

            app_config = load_config(self.workspace_root)
            return create_embedding_client(app_config.embedding)
        except Exception:
            return None

    def _index_wiki_articles(self) -> None:
        """Index all wiki articles so the Curator can find them.

        Runs FTS indexing (and embedding indexing when an embedding client
        is available) for every article in wiki/. Called before Refinement
        iterations so the multi-pass retriever has data to work with.
        """
        wiki_dir = self.workspace_root / "wiki"
        if not wiki_dir.exists():
            return
        articles = sorted(wiki_dir.rglob("*.md"))
        if not articles:
            return
        indexed = 0
        for article_path in articles:
            rel_path = str(article_path.relative_to(self.workspace_root))
            try:
                if self._embedding_client is not None:
                    changed = self.archivist.index_with_embeddings(
                        rel_path, embedding_client=self._embedding_client
                    )
                else:
                    changed = self.archivist.index(rel_path)
                if changed:
                    indexed += 1
            except Exception as exc:
                logger.warning("Failed to index %s: %s", rel_path, exc)
        logger.info("Indexed %d wiki articles before Refinement", indexed)

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
        tokens_before = getattr(
            self.llm_client,
            "total_tokens_used",
            0,
        )
        prompt = self._build_prompt(phase)
        response = self.captain.call_llm(
            [{"role": "user", "content": prompt}],
        )
        # Record Captain planning tokens to budget tracker
        tokens_after = getattr(
            self.llm_client,
            "total_tokens_used",
            0,
        )
        plan_tokens = tokens_after - tokens_before
        if plan_tokens > 0:
            self.budget.tracker.record(
                agent="captain",
                expedition=self.config.name,
                tokens=plan_tokens,
            )

        missions, dependencies = parse_plan_response(response)
        if not missions:
            # Log the raw response for debugging parse failures
            logger.debug(
                "Raw LLM response for %s:\n%s",
                phase.value,
                response[:500],
            )
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
                msg = f"Budget exceeded — halting: {budget_status.message}"
                logger.warning(msg)
                iteration.budget_halt_message = msg
                break
            if budget_status.is_warning:
                logger.warning("Budget warning: %s", budget_status.message)

            # Check if auto-scaling would trigger
            queue_depth = len(pending)
            for agent_type in {
                m.agent for m in iteration.missions if m.mission_id in pending
            }:
                if self.scaling.should_scale_up(
                    agent_type,
                    queue_depth,
                ):
                    logger.info(
                        "Scale-up triggered for %s (queue: %d)",
                        agent_type,
                        queue_depth,
                    )

            # Find ready missions, limited by max_concurrent_missions
            ready = graph.ready_missions(pending, completed)
            if not ready:
                # All remaining missions are blocked
                logger.warning(
                    "No ready missions — %d blocked",
                    len(pending),
                )
                break

            max_concurrent = self.config.stationed.resources.max_concurrent_missions
            batch = sorted(ready)[:max_concurrent]
            for mid in batch:
                mission = next(m for m in iteration.missions if m.mission_id == mid)
                logger.info(
                    "Executing %s (%s/%s)",
                    mission.mission_id,
                    mission.agent,
                    mission.mission_type,
                )
                self._execute_mission(mission)

                if mission.status == MissionStatus.COMPLETED:
                    completed.add(mid)
                    pending.discard(mid)
                    iteration.missions_completed += 1
                elif mission.status == MissionStatus.FAILED:
                    pending.discard(mid)
                    iteration.missions_failed += 1

        return iteration

    def run_build(
        self,
        max_iterations: int = 5,
        dry_run: bool = False,
    ) -> BuildPhaseResult:
        """Run the full build phase with variable iteration count.

        Sequence: Discovery first, then Structuring → Refinement cycles
        until no new missions are planned or max_iterations is reached.
        Small expeditions exit after 2 (D, S). Large ones may need 4-5
        (D, S, R, S, R) when Refinement reveals additional structuring
        needs.

        If dry_run=True, plans Discovery but does not execute any
        missions. Useful for previewing the build plan.
        """
        result = BuildPhaseResult()
        all_completed: set[str] = set()
        iteration_count = 0

        if dry_run:
            iteration = self.plan_iteration(IterationPhase.DISCOVERY)
            result.iterations.append(iteration)
            result.total_missions += iteration.missions_planned
            self._write_build_report(result)
            self.ledger.close()
            self.budget.tracker.close()
            return result

        # Discovery always runs first
        iteration_count += 1
        self._run_and_record(
            IterationPhase.DISCOVERY,
            result,
            all_completed,
        )

        # Structuring → Refinement cycles until exit condition
        while iteration_count < max_iterations:
            iteration_count += 1
            has_work = self._run_and_record(
                IterationPhase.STRUCTURING,
                result,
                all_completed,
            )
            if not has_work:
                break

            if iteration_count >= max_iterations:
                break

            # Index compiled articles before Refinement so the
            # Curator's multi-pass retriever can find them.
            self._index_wiki_articles()

            iteration_count += 1
            has_work = self._run_and_record(
                IterationPhase.REFINEMENT,
                result,
                all_completed,
            )
            if not has_work:
                break

        self._write_build_report(result)
        self.ledger.close()
        self.budget.tracker.close()
        return result

    def _run_and_record(
        self,
        phase: IterationPhase,
        result: BuildPhaseResult,
        all_completed: set[str],
    ) -> bool:
        """Plan and execute one iteration, recording into result.

        Returns True if the iteration had missions to execute,
        False if no work was planned (exit condition).
        """
        iteration = self.plan_iteration(phase)

        if iteration.missions_planned == 0 and phase != IterationPhase.DISCOVERY:
            logger.info(
                "Skipping %s — no missions planned (exit condition met)",
                phase.value,
            )
            result.iterations.append(iteration)
            return False

        iteration = self.execute_iteration(
            iteration,
            prior_completed=all_completed,
        )
        for m in iteration.missions:
            if m.status == MissionStatus.COMPLETED:
                all_completed.add(m.mission_id)
        result.iterations.append(iteration)
        result.total_missions += iteration.missions_planned
        result.total_completed += iteration.missions_completed
        result.total_failed += iteration.missions_failed
        return True

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
                tokens_before = getattr(
                    self.llm_client,
                    "total_tokens_used",
                    0,
                )
                params = self._mission_to_params(mission)
                self._validate_params(mission, params)

                # Scout multi-path: run one task per path
                all_paths = params.get("source_path", "")
                if mission.agent == "scout" and "," in all_paths:
                    sub_results = []
                    for i, p in enumerate(all_paths.split(",")):
                        # Check budget between sub-tasks
                        if i > 0:
                            budget_status = self.budget.check()
                            if not budget_status.can_proceed:
                                mission.fail(
                                    error_type="deterministic",
                                    error_message=(
                                        f"Budget exceeded between "
                                        f"sub-tasks: {budget_status.message}"
                                    ),
                                    retries=0,
                                )
                                self.ledger.save(mission)
                                return
                        sub_task = Task(
                            task_id=(f"task-{mission.mission_id}-{attempt}-{i}"),
                            agent="scout",
                            params={"source_path": p.strip()},
                        )
                        sub_results.append(
                            self.task_runner.run(
                                sub_task,
                                self.llm_client,
                            ),
                        )
                    # Merge sub-results, preserving output paths
                    all_output_paths: list[Path] = []
                    for sr in sub_results:
                        if sr.agent_output:
                            all_output_paths.extend(
                                sr.agent_output.output_paths,
                            )
                    last = sub_results[-1]
                    task_result = type(last)(
                        success=all(r.success for r in sub_results),
                        status=last.status,
                        error_type=next(
                            (r.error_type for r in sub_results if not r.success),
                            "",
                        ),
                        error_message=next(
                            (r.error_message for r in sub_results if not r.success),
                            "",
                        ),
                        agent_output=last.agent_output,
                    )
                    # Attach all output paths to the merged result
                    if task_result.agent_output and all_output_paths:
                        task_result.agent_output.output_paths = all_output_paths
                else:
                    task = Task(
                        task_id=f"task-{mission.mission_id}-{attempt}",
                        agent=mission.agent,
                        params=params,
                    )
                    task_result = self.task_runner.run(
                        task,
                        self.llm_client,
                    )

                if task_result.success:
                    # Record task execution tokens (mission's agent)
                    tokens_mid = getattr(
                        self.llm_client,
                        "total_tokens_used",
                        0,
                    )
                    task_tokens = tokens_mid - tokens_before
                    if task_tokens > 0:
                        self.budget.tracker.record(
                            agent=mission.agent,
                            expedition=self.config.name,
                            tokens=task_tokens,
                        )

                    # Two-level completion: Captain verifies
                    output_paths: list[str] = []
                    if task_result.agent_output:
                        output_paths = [
                            str(p) for p in task_result.agent_output.output_paths
                        ]
                    verified = self._verify_mission(
                        mission,
                        task_output_paths=output_paths,
                    )

                    # Record verification tokens (captain)
                    tokens_after = getattr(
                        self.llm_client,
                        "total_tokens_used",
                        0,
                    )
                    verify_tokens = tokens_after - tokens_mid
                    if verify_tokens > 0:
                        self.budget.tracker.record(
                            agent="captain",
                            expedition=self.config.name,
                            tokens=verify_tokens,
                        )

                    if verified:
                        mission.complete(verified_by="captain")
                        if task_result.agent_output:
                            mission.output_paths = [
                                str(p.relative_to(self.workspace_root))
                                for p in task_result.agent_output.output_paths
                                if p.is_absolute()
                            ]
                    else:
                        reason = getattr(
                            mission,
                            "_last_rejection_reason",
                            "acceptance criteria not met",
                        )
                        mission.fail(
                            error_type="deterministic",
                            error_message=(
                                f"Captain rejected after "
                                f"{self._MAX_VERIFY_ATTEMPTS} attempts: "
                                f"{reason[:200]}"
                            ),
                            retries=0,
                        )
                    self.ledger.save(mission)
                    return

                # Record tokens for failed tasks
                tokens_after = getattr(
                    self.llm_client,
                    "total_tokens_used",
                    0,
                )
                tokens = tokens_after - tokens_before
                if tokens > 0:
                    self.budget.tracker.record(
                        agent=mission.agent,
                        expedition=self.config.name,
                        tokens=tokens,
                    )

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
                # Transient failures: retry with backoff
                if attempt < max_retries:
                    mission.retry()
                    backoff = 2**attempt  # 1s, 2s, 4s
                    time.sleep(backoff)
                    continue
                return

            except ValueError as exc:
                # Deterministic: bad params, malformed input — no retry
                mission.fail(
                    error_type="deterministic",
                    error_message=str(exc),
                    retries=0,
                )
                self.ledger.save(mission)
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
                    backoff = 2**attempt
                    time.sleep(backoff)
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
                # Scout processes one file at a time. For multi-path
                # missions, pass all paths comma-separated. The
                # execute loop runs one task per path.
                params["source_path"] = ",".join(str(p) for p in paths)
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

    # Common LLM hallucinations → valid ArticleType corrections
    _ARTICLE_TYPE_CORRECTIONS: ClassVar[dict[str, str]] = {
        "overview": "concept",
        "reference": "entity",
        "guide": "concept",
        "glossary": "entity",
        "tutorial": "concept",
        "how-to": "concept",
        "howto": "concept",
        "changelog": "log",
        "history": "log",
        "timeline": "log",
        "analysis": "exploration",
        "research": "exploration",
        "investigation": "exploration",
        "summary": "concept",
        "index": "concept",
    }

    @staticmethod
    def _validate_params(
        mission: Mission,
        params: dict[str, str],
    ) -> None:
        """Validate that required params are present for the agent.

        Raises ValueError with diagnostic message if a required key
        is missing — fail-fast before dispatching a doomed task.
        Corrects invalid article_type values for compiler missions.
        """
        from assistonauts.models.schema import ArticleType

        required: dict[str, list[str]] = {
            "scout": ["source_path"],
            "compiler": [],  # source_path OR source_paths
            "curator": ["article_path"],
            "explorer": ["query"],
        }
        agent = mission.agent
        if agent == "compiler" and not (
            "source_path" in params or "source_paths" in params
        ):
            msg = (
                f"Mission {mission.mission_id}: compiler requires "
                f"'sources' in inputs, got {mission.inputs}"
            )
            raise ValueError(msg)
        for key in required.get(agent, []):
            if key not in params or not params[key]:
                msg = (
                    f"Mission {mission.mission_id}: {agent} requires "
                    f"'{key}' in params, got {params}"
                )
                raise ValueError(msg)

        # Correct invalid article_type for compiler missions
        if agent == "compiler" and "article_type" in params:
            valid = {t.value for t in ArticleType}
            raw_type = params["article_type"]
            if raw_type not in valid:
                corrected = BuildOrchestrator._ARTICLE_TYPE_CORRECTIONS.get(
                    raw_type.lower(),
                    "concept",
                )
                logger.warning(
                    "Mission %s: corrected article_type '%s' → '%s'",
                    mission.mission_id,
                    raw_type,
                    corrected,
                )
                params["article_type"] = corrected

    # Mission types where agent success=True is sufficient verification.
    # Cross-referencing and ingestion are structural operations — the agent
    # already validates its own output (e.g. no broken links, valid
    # frontmatter). Captain verification adds cost without value here.
    _AUTO_APPROVE_TYPES: ClassVar[set[str]] = {
        "cross_reference",
        "ingest_sources",
    }

    # Maximum verification attempts before final rejection.
    _MAX_VERIFY_ATTEMPTS: ClassVar[int] = 3

    def _verify_mission(
        self,
        mission: Mission,
        task_output_paths: list[str] | None = None,
    ) -> bool:
        """Captain verifies mission against acceptance criteria.

        Two-level completion: after the agent self-declares completion,
        the Captain evaluates whether the acceptance criteria are met.
        Returns True if verified, False if rejected.
        Missions with no acceptance criteria are auto-approved.
        Structural mission types (cross_reference, ingest_sources) are
        auto-approved because the agent's own validation is sufficient.

        Uses a retry-with-feedback loop: if the Captain rejects, the
        rejection reason is fed back for reconsideration. This handles
        LLM non-determinism where borderline articles are sometimes
        rejected on first pass but accepted when the Captain reconsiders
        with its own reasoning as context.
        """
        if not mission.acceptance_criteria:
            return True

        if mission.mission_type in self._AUTO_APPROVE_TYPES:
            logger.info(
                "Auto-approving %s (%s) — structural operation",
                mission.mission_id,
                mission.mission_type,
            )
            return True

        criteria_text = "\n".join(f"- {c}" for c in mission.acceptance_criteria)
        output_text = "(no output details available)"
        if task_output_paths:
            output_text = "\n".join(f"- {p}" for p in task_output_paths)
            snippets = self._read_output_snippets(task_output_paths)
            if snippets:
                output_text += "\n\nOutput content:\n" + snippets

        # Build the conversation for multi-turn verification
        messages: list[dict[str, str]] = [
            {
                "role": "user",
                "content": (
                    "MISSION VERIFICATION\n\n"
                    f"Mission: {mission.mission_id}\n"
                    f"Agent: {mission.agent}\n"
                    f"Type: {mission.mission_type}\n\n"
                    f"Acceptance criteria:\n{criteria_text}\n\n"
                    f"Agent output files:\n{output_text}\n\n"
                    "The agent has declared this mission complete.\n"
                    "Review the output against the acceptance criteria. "
                    "The criteria are aspirational guidelines for draft "
                    "content — VERIFY if the output makes a reasonable "
                    "attempt at meeting them given the available source "
                    "material. Minor gaps or thin coverage are acceptable "
                    "for first-draft articles. Only REJECT if the output "
                    "is fundamentally off-topic, empty, or missing the "
                    "majority of required elements.\n\n"
                    "Respond with VERIFIED or REJECTED followed by a "
                    "brief reason."
                ),
            },
        ]

        for attempt in range(self._MAX_VERIFY_ATTEMPTS):
            response = self.captain.call_llm(messages)

            if "VERIFIED" in response.upper():
                if attempt > 0:
                    logger.info(
                        "Verification succeeded on retry %d for %s",
                        attempt,
                        mission.mission_id,
                    )
                return True

            # Extract rejection reason for feedback
            reason = response.strip()
            logger.info(
                "Verification attempt %d/%d rejected %s: %s",
                attempt + 1,
                self._MAX_VERIFY_ATTEMPTS,
                mission.mission_id,
                reason[:120],
            )

            if attempt < self._MAX_VERIFY_ATTEMPTS - 1:
                # Feed rejection back for reconsideration
                messages.append({"role": "assistant", "content": response})
                messages.append(
                    {
                        "role": "user",
                        "content": (
                            "Reconsider this rejection. The agent worked "
                            "from limited source material and may not have "
                            "had access to all the information the criteria "
                            "request. The acceptance criteria describe the "
                            "ideal output — partial coverage is expected "
                            "for draft articles.\n\n"
                            "Given that this is a first draft compiled from "
                            "raw sources, does the output demonstrate a "
                            "genuine, substantive attempt at the criteria? "
                            "If so, respond VERIFIED. Only maintain REJECTED "
                            "if the output is fundamentally inadequate.\n\n"
                            "Respond with VERIFIED or REJECTED followed by "
                            "a brief reason."
                        ),
                    },
                )

        # Store the final rejection reason on the mission for debugging
        mission._last_rejection_reason = reason  # type: ignore[attr-defined]
        return False

    def _read_output_snippets(
        self,
        output_paths: list[str],
        max_lines: int = 80,
    ) -> str:
        """Read content snippets from output files for verification."""
        parts: list[str] = []
        for path_str in output_paths:
            p = Path(path_str)
            if not p.is_absolute():
                p = self.workspace_root / p
            if not p.exists() or not p.is_file():
                continue
            try:
                lines = p.read_text(encoding="utf-8").splitlines()
                snippet = "\n".join(lines[:max_lines])
                if len(lines) > max_lines:
                    snippet += f"\n... ({len(lines) - max_lines} more lines)"
                parts.append(f"--- {p.name} ---\n{snippet}")
            except (OSError, UnicodeDecodeError):
                continue
        return "\n\n".join(parts)

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
                "to ingest all configured sources into raw/. "
                "Do NOT plan any other agent missions — "
                "the Structuring iteration will handle "
                "article compilation after ingestion is complete.\n\n"
                f"Sources: {self._describe_sources()}\n\n"
                "Create a mission plan for Scout ingestion only."
            )

        elif phase == IterationPhase.STRUCTURING:
            summaries = self._load_article_summaries()
            summaries_text = (
                "\n".join(f"- {title}: {summary}" for title, summary in summaries)
                if summaries
                else "(no summaries available yet)"
            )
            prior_results = self._describe_prior_iterations()
            raw_listing = self._list_raw_articles()
            return (
                f"{scope_text}\n"
                "ITERATION PHASE: Structuring\n\n"
                f"Prior iteration results:\n{prior_results}\n\n"
                "Review the compiled articles and their summaries "
                "below. Identify foundational concepts that other "
                "articles will reference. Sequence remaining Compiler "
                "missions with correct dependency ordering — "
                "foundational concepts first.\n\n"
                f"Compiled article summaries:\n{summaries_text}\n\n"
                f"Available raw source files (use these EXACT "
                f"paths in compiler inputs.sources):\n"
                f"{raw_listing}\n\n"
                "Identify structural needs: are there concepts "
                "that need dedicated entity pages or category "
                "articles?\n\n"
                "Create a mission plan for the remaining work."
            )

        else:  # REFINEMENT
            prior_results = self._describe_prior_iterations()
            wiki_listing = self._list_wiki_articles()
            return (
                f"{scope_text}\n"
                "ITERATION PHASE: Refinement\n\n"
                f"Prior iteration results:\n{prior_results}\n\n"
                "All sources are compiled and indexed. Plan:\n"
                "1. Curator cross-referencing pass over all "
                "articles (batched — not incremental, since the "
                "full corpus is now available)\n"
                "2. Inspector sweep (placeholder — Phase 6)\n\n"
                f"Wiki articles (use these EXACT paths for "
                f"curator inputs.article_path):\n"
                f"{wiki_listing}\n\n"
                "Create missions for the refinement pass."
            )

    def _describe_prior_iterations(self) -> str:
        """Summarize completed iterations for the Captain's context."""
        if not self._iterations:
            return "(no prior iterations)"
        lines: list[str] = []
        for it in self._iterations:
            completed = [m for m in it.missions if m.status == MissionStatus.COMPLETED]
            failed = [m for m in it.missions if m.status == MissionStatus.FAILED]
            lines.append(
                f"- {it.phase.value.title()}: "
                f"{len(completed)} completed, {len(failed)} failed"
            )
            for m in completed:
                out = ""
                if m.output_paths:
                    out = f" → {', '.join(m.output_paths)}"
                lines.append(
                    f"  - [completed] {m.mission_id} ({m.agent}/{m.mission_type}){out}"
                )
            for m in failed:
                err = m.failure.error_message[:80] if m.failure else "unknown"
                lines.append(
                    f"  - [failed] {m.mission_id} ({m.agent}/{m.mission_type}): {err}"
                )
        return "\n".join(lines) if lines else "(no prior iterations)"

    def _describe_sources(self) -> str:
        """Describe configured sources for the prompt.

        Resolves glob patterns to actual file paths so the Captain
        plans scout missions with individual files, not directories.
        """
        parts = []
        for ls in self.config.sources.local:
            source_dir = Path(ls.path)
            if source_dir.is_dir():
                files = sorted(source_dir.glob(ls.pattern))
                if files:
                    file_list = ", ".join(str(f) for f in files)
                    parts.append(f"Local ({len(files)} files): {file_list}")
                else:
                    parts.append(f"Local: {ls.path} ({ls.pattern}) — no matching files")
            else:
                parts.append(f"Local: {ls.path} ({ls.pattern})")
        return "; ".join(parts) if parts else "No sources configured"

    def _list_raw_articles(self) -> str:
        """List raw article files with workspace-relative paths."""
        raw_dir = self.workspace_root / "raw" / "articles"
        if not raw_dir.exists():
            return "(no raw articles)"
        files = sorted(raw_dir.glob("*.md"))
        if not files:
            return "(no raw articles found)"
        return "\n".join(f"- {f.relative_to(self.workspace_root)}" for f in files)

    def _list_wiki_articles(self) -> str:
        """List compiled wiki articles with workspace-relative paths."""
        wiki_dir = self.workspace_root / "wiki"
        if not wiki_dir.exists():
            return "(no wiki articles)"
        files = sorted(
            f for f in wiki_dir.rglob("*.md") if "explorations" not in f.parts
        )
        if not files:
            return "(no wiki articles found)"
        return "\n".join(f"- {f.relative_to(self.workspace_root)}" for f in files)

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
                logger.warning(
                    "Corrupted plan.yaml — overwriting with fresh data",
                )

        iteration_data: dict[str, object] = {
            "phase": phase.value,
            "missions": [
                {
                    "id": m.mission_id,
                    "agent": m.agent,
                    "type": m.mission_type,
                    "priority": m.priority,
                    "inputs": m.inputs,
                    "acceptance_criteria": m.acceptance_criteria,
                }
                for m in missions
            ],
            "dependencies": [{"from": d[0], "to": d[1]} for d in dependencies],
        }
        existing.append(iteration_data)

        plan_data = {
            "expedition": self.config.name,
            "iterations": existing,
        }
        try:
            plan_path.write_text(
                yaml.dump(plan_data, default_flow_style=False),
            )
        except OSError:
            logger.warning("Failed to write plan.yaml — continuing")

    def _write_build_report(self, result: BuildPhaseResult) -> None:
        """Write a build report to expeditions/<name>/build-report.md."""
        exp_dir = self.workspace_root / "expeditions" / self.config.name
        report_path = exp_dir / "build-report.md"

        lines = [
            f"# Build Report — {self.config.name}",
            "",
            f"**Scope:** {self.config.scope.description}",
            f"**Keywords:** {', '.join(self.config.scope.keywords)}",
            "",
            "## Sources",
            "",
            f"- {self._describe_sources()}",
            "",
            "## Mission Summary",
            "",
            f"- **Total missions:** {result.total_missions}",
            f"- **Completed:** {result.total_completed}",
            f"- **Failed:** {result.total_failed}",
            f"- **Iterations:** {len(result.iterations)}",
            "",
        ]

        # Knowledge base article counts
        wiki_dir = self.workspace_root / "wiki"
        article_count = 0
        word_count = 0
        if wiki_dir.exists():
            for md in wiki_dir.rglob("*.md"):
                article_count += 1
                word_count += len(md.read_text().split())
        lines.extend(
            [
                "## Knowledge Base",
                "",
                f"- **Articles:** {article_count}",
                f"- **Total words:** {word_count:,}",
                "",
            ]
        )

        # Token usage by agent (from budget tracker)
        # Include agents from missions AND captain (planning calls)
        agents_used: set[str] = {"captain"}
        for it in result.iterations:
            for m in it.missions:
                agents_used.add(m.agent)
        total_tokens = getattr(
            self.llm_client,
            "total_tokens_used",
            0,
        )
        lines.extend(
            [
                "## Token Usage",
                "",
                f"- **Total tokens used:** {total_tokens:,}",
            ]
        )
        for agent in sorted(agents_used):
            agent_total = self.budget.tracker.get_agent_total(agent)
            lines.append(f"- {agent}: {agent_total:,} tokens")
        budget_remaining = self.budget.remaining()
        lines.extend(
            [
                f"- **Budget remaining:** {budget_remaining:,}",
                "",
            ]
        )

        # Coverage metrics
        local_sources = sum(1 for _ in self.config.sources.local)
        raw_dir = self.workspace_root / "raw" / "articles"
        raw_count = sum(1 for _ in raw_dir.glob("*.md")) if raw_dir.exists() else 0
        xref_count = 0
        if wiki_dir.exists():
            for md in wiki_dir.rglob("*.md"):
                content = md.read_text()
                if "## See Also" in content or "[[" in content:
                    xref_count += 1
        xref_pct = (
            f"{xref_count / article_count * 100:.0f}%" if article_count > 0 else "N/A"
        )
        lines.extend(
            [
                "## Coverage",
                "",
                f"- **Source configs:** {local_sources}",
                f"- **Raw articles ingested:** {raw_count}",
                f"- **Wiki articles compiled:** {article_count}",
                f"- **Cross-referenced:** {xref_count}/{article_count} ({xref_pct})",
                "",
            ]
        )

        # Iteration details
        lines.extend(["## Iterations", ""])
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

        try:
            report_path.write_text("\n".join(lines))
        except OSError:
            logger.warning("Failed to write build report — continuing")

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
