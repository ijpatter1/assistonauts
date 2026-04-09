# Assistonauts — Development Plan & Requirements

## Project Vision

Assistonauts is a framework for building and maintaining LLM-powered knowledge bases using specialized AI agents. Raw source material — papers, articles, repos, datasets, images — is ingested, compiled into a structured interlinked markdown wiki, indexed for hybrid retrieval, quality-checked for integrity, and continuously maintained by a team of stationed agents.

The core insight: traditional RAG rediscovers knowledge from scratch on every query. Assistonauts compiles knowledge once, keeps it current, and uses RAG only for routing — finding which compiled articles are relevant — while the LLM reasons over full, structured documents. The result is a knowledge base that compounds over time rather than degrading.

The system is built around six specialized agents (Captain, Scout, Compiler, Curator, Inspector, Explorer) supported by a deterministic knowledge base operating system (the Archivist). Each agent has a defined responsibility boundary, a set of zero-inference toolkit utilities, and uses LLM inference only for judgment calls. The framework deploys first as a CLI for local development and dogfooding, with self-hosted and SaaS deployment surfaces planned for later phases.

---

## Glossary

- **Task** — A single agent operation: one agent, one action, defined inputs and outputs. Tasks are atomic and independently executable. Example: "Compiler: compile these 3 sources into an article titled X of type Y." The task runner executes tasks with YAML audit trails and failure classification (transient vs deterministic).

- **Mission** — A scoped objective that decomposes into an ordered sequence of tasks, potentially spanning multiple agents. Has acceptance criteria, a state machine (pending → running → completed/failed/stale), and a dependency graph. Example: "Build a knowledge base from this book" decomposes into ingestion tasks, a triage step, compilation tasks, indexing, and cross-referencing. Missions are planned by the Captain and tracked in the mission ledger.

- **Triage** — The editorial judgment step between raw source ingestion and compilation. Determines what articles to create, what type each should be, which sources group together, and what titles to use. This is a Compiler capability (plan mode), not a Captain responsibility. The Captain sequences and orchestrates; the Compiler makes editorial decisions within its domain.

Note: The codebase currently uses "mission" where it means "task" (the Phase 2 `MissionRunner` is really a task runner). A vocabulary refactor is tracked in Phase 2 deliverables. The original spec (`assistonauts-spec.md`) uses "mission" correctly in the multi-step sense.

---

## Phase 1 — Core Infrastructure + Scout

**Goal:** Establish the foundation that every subsequent phase builds on — workspace management, config system, base agent class, LLM client, shared toolkit, and the first working agent (Scout).

**Deliverables:**

1. Workspace initialization (`assistonauts init`) — creates the full directory structure (`raw/`, `wiki/`, `index/`, `audits/`, `expeditions/`, `station-logs/`, `.assistonauts/`), initializes git repo, writes `.gitignore` for derived data
2. Config loading system — YAML parser for expedition configs, agent configs, and global settings with validation and sensible defaults
3. Base agent class with toolkit integration — `Agent` base class with injectable LLM client, toolkit registration, owned/readable directory enforcement, and structured logging. Designed for testability (see Testing Strategy in spec)
4. LLM client wrapper (litellm) — provider-agnostic inference calls with record/replay mode for test fixtures, configurable role-to-provider mapping
5. Shared toolkit — logger (structured, to mission log files), config reader, cache interface, file I/O with ownership boundary enforcement
6. Content hash cache (manifest) — SHA-256 content tracking in `index/manifest.json`, skip-if-unchanged logic, downstream dependency tracking
7. Scout agent — role implementation with system prompt, relevance filtering (keyword match + optional LLM check), source ingestion pipeline
8. Scout toolkit — format converters (PDF/HTML/DOCX to markdown via markitdown), web clipper (fetch + extract + download assets), content hasher, deduplication checker (simhash/minhash)
9. Contract test infrastructure — pytest fixtures, LLM client replay mode integration, assertion helpers for agent output structure validation
10. Scout contract tests and recorded fixtures — structural validation of Scout output (valid markdown, assets referenced correctly, frontmatter present)
11. CLI entry point — `assistonauts init` and `assistonauts scout ingest <path-or-url>` commands via Click + Rich

**Why this is Phase 1:** Everything else depends on the workspace structure, config system, base agent class, and LLM client. The Scout is the natural first agent because it has no upstream dependencies — it brings material into the system. Getting the base agent class right here is critical since every subsequent agent inherits it.

**Validation:** Initialize a workspace, drop a PDF into `raw/`, run Scout to convert it to markdown. Content hash prevents re-processing on second run. Contract tests verify Scout output structure. The base agent class supports LLM client injection for testing.

---

## Phase 2 — Compiler + Task Runner

**Goal:** Build the compilation pipeline — the Compiler agent that transforms raw sources into structured wiki articles, and the task runner that executes and tracks individual agent operations.

**Deliverables:**

1. Wiki schema definition (`_schema.md`) — article templates per type (concept, entity, log, exploration), required frontmatter fields, categorization taxonomy, naming conventions, backlink formatting rules
2. Template engine — apply schema templates to new articles so the LLM fills structured sections rather than generating format from scratch
3. Compiler agent — role implementation with system prompt incorporating expedition scope as editorial lens, compilation pipeline for new sources and diff-oriented recompilation for updates
4. Compiler toolkit — diff generator (structured diff for LLM reasoning), article stats (word count, reading time, source count)
5. Compiler content summary generation — each compilation produces a content summary as a deliverable, optimized for downstream triage by Curator and Explorer
6. Task runner — single task execution with YAML audit trail, failure classification (transient vs deterministic), retry logic for transient errors, fail-fast for deterministic errors. (Note: currently named `MissionRunner` in codebase — rename tracked in deliverable 12)
7. Task-level git commits — task runner commits after each completed task with task ID and agent in commit message
8. Compiler contract tests and recorded fixtures — structural validation (valid frontmatter, schema-conformant sections, content summary present, source citations included)
9. CLI: `assistonauts task run --agent compiler` — execute a single Compiler task from the command line
10. Multi-source compilation — Compiler accepts multiple source paths (`--source` repeated), concatenates source content in order, tracks all source hashes in manifest for skip-if-unchanged logic, lists all sources in article frontmatter
11. Compiler plan mode — `compiler.plan()` reads a set of raw sources, analyzes their content and structure, and proposes a compilation plan: what articles to create, article types, source groupings, and titles. Returns a list of task definitions ready for execution. Uses LLM inference for editorial judgment. The Captain orchestrates when and how plans are executed, but the Compiler owns the editorial decisions. Plans are persisted to `.assistonauts/plans/` as YAML artifacts for audit trail. `plan --execute` routes each compilation through the task runner for YAML audit trails and optional git commits.
12. Task/Mission vocabulary refactor — rename `MissionRunner` → `TaskRunner`, `Mission` → `Task`, `MissionResult` → `TaskResult`, `run_mission()` → `run_task()`, `missions/` → `tasks/`, CLI `mission run` → `task run`. Aligns codebase with glossary: tasks are atomic agent operations, missions are multi-step objectives (Phase 5).

**Why this is Phase 2:** The Compiler depends on the base agent class, LLM client, config system, and Scout output from Phase 1. The task runner is introduced here because Compiler work is the first agent workflow that needs tracking and audit trails. Compiler plan mode is essential for the pipeline to work without manual editorial decisions — it bridges the gap between raw ingestion and structured compilation.

**Validation:** Run Scout to ingest sources, then Compiler plan mode to propose articles, then task runner to compile. Verify plan mode produces sensible article types, groupings, and titles from real content. Multi-source: ingest multiple page images, plan mode groups them correctly, compile into a single article — verify all sources listed in frontmatter and content is coherent.

---

## Phase 3 — Archivist System + Curator + Hybrid RAG

**Goal:** Build the Archivist (deterministic knowledge base operating system), hybrid retrieval, the multi-pass retrieval system, and the Curator agent for cross-referencing.

**Deliverables:**

1. Archivist system core — main `Archivist` class with service interface (`index()`, `search()`, `reindex_batch()`, `get_staleness()`, `get_downstream()`), not an agent — no LLM inference
2. Embedding generation and storage — embedding model API calls via litellm, chunking, batching, storage in `index/assistonauts.db` (sqlite-vec)
3. FTS indexing — SQLite FTS5 insert/update/delete for keyword-based retrieval
4. Hybrid retrieval — vector similarity + FTS keyword search, reciprocal rank fusion reranking, configurable relevance floor, no arbitrary result cap
5. Dual summary storage — retrieval summaries (deterministic keyword extraction) and content summaries (received from Compiler) in `index/summaries.jsonl`
6. Manifest management — full lineage tracking, staleness graphs, embedding version tracking, summary staleness detection
7. Multi-pass retrieval system — shared module (`rag/multi_pass.py`) with Pass 1 (broad scan, zero inference), Pass 2 (triage on summaries, cheap inference), Pass 3 (deep read, targeted inference), Pass 4 (weak match resolution)
8. Short-circuit mode — bypass multi-pass for small knowledge bases (below configurable article/word count threshold), load all articles directly
9. Curator agent — role implementation with system prompt, singleton enforcement, cross-referencing pipeline (bidirectional: updates both the target article AND existing articles that should reference it), uses multi-pass retrieval system for link discovery (not raw hybrid_search), strong/weak match distinction (strong → bidirectional backlinks, weak → "See also" only), proposal generation for structural needs
10. Curator toolkit — backlink scanner (parse links, build graph, identify backlink targets), graph analyzer (connectivity metrics, orphan detection, cluster density)
11. Embedding cache — embedding version tracking, recompute only when content hash changes
12. LLM response cache — SHA-256 prompt hash keying, SQLite backend, configurable TTL, flush per agent/expedition
13. Retroactive cross-referencing — Curator pass over all indexed articles to add bidirectional backlinks and "See also" sections, using multi-pass retrieval for link discovery
14. CLI: `assistonauts status` — expedition and knowledge base status overview
15. Image ingestion in Scout — vision model support (Gemma 4 via litellm) for image files (.png, .jpg, .jpeg, .gif, .webp), sends images to multimodal LLM for text extraction and markdown conversion, integrates with existing Scout ingestion pipeline
16. CLI: `assistonauts index` — index all wiki articles into the Archivist (FTS + embeddings), with `--reindex` flag to force reindexing of unchanged articles
17. CLI: `assistonauts curate` — run Curator cross-referencing over all indexed articles, with `--proposals` flag to show structural improvement proposals
18. Batch ingestion CLI — `scout ingest` accepts multiple file arguments or glob patterns, ingesting each in sequence

**Why this is Phase 3:** The Archivist depends on compiled articles (Phase 2). The Curator depends on the Archivist's retrieval interface. The multi-pass retrieval system needs both the Archivist and a meaningful corpus to validate against. This is the phase where the knowledge base becomes interconnected. Image ingestion and the index/curate CLI commands complete the manual build chain so the full pipeline can be tested end-to-end with real content before Phase 4.

**Validation:** Compile 10+ articles, Archivist indexes them with dual summaries, verify retrieval quality. Curator cross-references a new article — verify multi-pass linking discovers all relevant connections. Verify Phase 1-2 articles are retroactively linked. Ingest an image file via Scout using vision model — verify extracted text is reasonable markdown. Run the full manual chain: `scout ingest` → `plan --execute` → `index` → `curate` → `status`.

---

## Phase 4 — Explorer + Interactive Mode

**Goal:** Build the Explorer agent for query synthesis and an interactive REPL for human-driven Q&A against the knowledge base.

**Deliverables:**

1. Explorer agent — role implementation with system prompt, query flow via multi-pass retrieval, answer synthesis with citations to specific wiki articles
2. Explorer toolkit — citation formatter, context budget calculator (recommend include/exclude to fit context window), output renderer (markdown, Marp slides, matplotlib charts)
3. Exploration filing — save valuable answers to `wiki/explorations/` with proper frontmatter, indexed by Archivist but not cross-linked into main wiki until promoted
4. Interactive REPL — Click-based CLI session for human-driven Q&A, conversational flow, optional answer filing
5. Explorer contract tests and recorded fixtures — structural validation (citations to real articles, answer format, context budget respected)
6. CLI: `assistonauts explore <expedition-name>` — launch interactive Explorer session

**Why this is Phase 4:** The Explorer depends on the Archivist's retrieval interface and the multi-pass retrieval system (Phase 3). It is the first consumer of the knowledge base from a human perspective — the payoff for all the compilation and indexing work.

**Validation:** Ask complex questions against the knowledge base and get synthesized answers with article citations. Verify multi-pass triage correctly identifies strong vs. weak matches. File an exploration and verify it appears in `wiki/explorations/`.

---

## Phase 5 — Captain + Expedition Orchestration

**Goal:** Build the Captain agent for expedition orchestration, the mission state machine, and the scaling/budget systems. The Captain creates missions (multi-step objectives) and sequences tasks within them. Editorial decisions (article types, groupings, titles) are delegated to the Compiler's plan mode — the Captain orchestrates when and how plans are executed.

**Deliverables:**

1. Captain agent — role implementation with two operational modes (planning mode for expedition decomposition into missions, operations mode for routine triage), system prompt with full state visibility
2. Captain toolkit — task queue manager (priority queue, dependency graph, topological sort), mission ledger (SQLite-backed mission state persistence), token budget tracker, schedule runner (cron evaluation), status aggregator
3. Iterative planning — plan → execute batch → observe → replan cycle for build phase. Captain creates missions, calls Compiler plan mode for editorial triage, then sequences the resulting tasks with dependency-aware ordering
4. Expedition lifecycle — `expedition.yaml` parsing, build phase orchestration across all agents, phase transition (build → stationed) as explicit human decision
5. Mission state machine — full lifecycle with acceptance criteria, agent-level checklists, status rollup to Captain view, failure classification integration. Missions contain ordered task sequences; tasks use the Phase 2 task runner for execution
6. Task dependency resolution — topological sort, foundational concepts compiled before articles that reference them, cascading task chains from Curator proposals
7. Deterministic scaling system — concurrent instances for Scout/Compiler/Explorer, Curator singleton enforcement, queue depth triggers, max instances, cooldown. Note: SQLite write concurrency is a known ceiling (see spec)
8. Deterministic budget system — daily token limits, per-agent tracking, warning thresholds, notifications to Captain for station logs
9. CLI: `assistonauts expedition create`, `assistonauts build` — create expeditions and run build phase

**Why this is Phase 5:** The Captain orchestrates all other agents, so it must be built after Scout (Phase 1), Compiler with plan mode (Phase 2), Archivist/Curator (Phase 3), and Explorer (Phase 4) are functional. The scaling system requires multiple agent types to be available for concurrent execution.

**Validation:** Create an expedition config, Captain produces missions by calling Compiler plan mode for editorial decisions, sequences tasks with dependency resolution, executes end-to-end with proper ordering. Test scaling with concurrent Compiler instances on a large source batch.

---

## Phase 6 — Inspector + Quality + Review

**Goal:** Build the Inspector agent for quality validation, the audit pipeline, and the human review system.

**Deliverables:**

1. Inspector agent — role implementation with deterministic-scan-first sweep pattern (tools run first, LLM analyzes flagged items only), finding severity levels (critical/warning/info)
2. Inspector toolkit — link checker, orphan detector, staleness scanner, duplicate detector (TF-IDF/simhash), schema validator, source freshness checker (HTTP HEAD/conditional GET)
3. Audit report generation — structured reports in `audits/` with findings, severity, recommended actions, sweep ID tagging
4. Finding-to-fix pipeline — Inspector findings generate Compiler fix tasks, auto-fix policy for low-risk findings, human review for high-risk
5. Human review queue — typed review items (inspector_finding, curator_proposal, scout_borderline, exploration_promotion, task_failure), Captain grouping/summarization, approve/dismiss/defer/inspect actions
6. Review storage and CLI — `expeditions/<n>/review/` YAML files, `assistonauts review` command with categorized display, drill-down, stale review escalation
7. Exploration promotion pipeline — Inspector technical quality check → human approval → standard ingestion flow (Compiler recompiles, Curator links)
8. Summary quality checks — Inspector validates Compiler-generated content summaries, flags stale/vague/missing summaries. First sweep should anticipate a batch of findings from Phases 2-5
9. Cycle guard — Inspector skips articles whose only changes since last sweep are finding-resolution commits, Curator backlink additions do not trigger re-audit

**Why this is Phase 6:** The Inspector validates the work of all other agents, so it needs a mature knowledge base with real content to inspect. The review queue requires the Captain (Phase 5) for grouping and mission routing. The exploration promotion pipeline requires both the Inspector and the existing Explorer filing mechanism (Phase 4).

**Validation:** Introduce deliberate contradictions, broken links, and gaps. Verify deterministic tools catch mechanical issues. Verify LLM catches semantic contradictions. Compiler fixes approved findings. File an exploration and verify the full promotion pipeline.

---

## Phase 7 — Stationed Mode

**Goal:** Enable continuous, autonomous operation — agents watch for changes, respond to events, and maintain the knowledge base on a schedule.

**Deliverables:**

1. Watch system — `watchdog` for local directories, RSS feed parser (`feedparser`), GitHub API poller for repo events, web page change detection (HTTP conditional GET + content diff)
2. Trigger/event system — event types (new_source, article_update, inspector_finding), trigger matching, event → task routing via Captain
3. Scheduled execution — cron expression evaluation for Scout watch intervals, Inspector sweep schedule, station log generation
4. Station log generation — weekly Captain reports with knowledge base health metrics (article count, word count, orphan rate, cross-referencing density, contradiction count, summary freshness, cache hit rates, token usage by agent)
5. Stale review item escalation — Captain tracks pending review age, escalates items older than configurable threshold in station logs
6. Cycle guards — Inspector sweep ID tagging prevents re-auditing just-fixed articles, Curator link-section edits distinguished from content edits
7. Pause/resume support — `assistonauts pause` halts all agent activity, `assistonauts resume` restarts from current state
8. CLI: `assistonauts station`, `assistonauts log`, `assistonauts pause`, `assistonauts resume`

**Why this is Phase 7:** Stationed mode orchestrates all agents in a continuous loop. Every component must be functional and validated before enabling autonomous operation. This is the capstone phase that transforms the framework from a manual tool into a self-maintaining system.

**Validation:** Station agents on autotrader expedition, add new experiment results, observe the full pipeline fire automatically (Scout → Compiler → Archivist → Curator → Inspector). Verify station log produces accurate health metrics. Test pause/resume.

---

## Dependencies & Risk Notes

### Phase Dependencies

```
Phase 1 (Core + Scout)
  └─► Phase 2 (Compiler + Task Runner)
        └─► Phase 3 (Archivist + Curator + RAG)
              ├─► Phase 4 (Explorer)
              └─► Phase 5 (Captain + Orchestration) ◄── also depends on Phase 4
                    └─► Phase 6 (Inspector + Review)
                          └─► Phase 7 (Stationed Mode)
```

### Risk Notes

1. **Base agent class is a critical path decision.** Phase 1's base agent class is inherited by every agent. Mistakes here compound. The injectable LLM client and toolkit registration patterns must be validated with Scout before proceeding to Phase 2. Budget time for iteration.

2. **SQLite concurrency ceiling.** All cache layers and the mission ledger use SQLite. With scaled agents (Phase 5), write contention is theoretically possible but practically negligible for v1 CLI (LLM API latency >> DB write time). Documented as a known ceiling. Postgres planned for server deployment.

3. **Content summary quality gap.** The Inspector (which validates summaries) arrives in Phase 6. Phases 2-5 operate on Compiler-generated summaries with no automated quality gate. Manual review during development mitigates this. The first Inspector sweep should plan for a remediation batch.

4. **Task retry classification.** Transient failures (API timeouts, rate limits) are retried automatically. Deterministic failures (context overflow, malformed input) are routed to the review queue immediately. Misclassifying a deterministic error as transient wastes tokens; misclassifying a transient error as deterministic creates unnecessary human review. The boundary may need tuning in practice.

5. **Multi-pass retrieval depends on summary quality.** A bad content summary causes the Curator or Explorer to miss relevant connections. This is documented in the spec as "Summary Quality as Infrastructure" — the Compiler's summary generation is core infrastructure, not a nice-to-have.

6. **External dependency: litellm.** The LLM client wraps litellm for provider-agnostic inference. If litellm introduces breaking changes or drops a provider, the wrapper layer isolates the impact. The record/replay mode for testing also reduces dependence on live API availability during development.
