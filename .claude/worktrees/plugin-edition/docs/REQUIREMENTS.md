# Assistonauts — Development Plan & Requirements

## Project Vision

Assistonauts is a framework for building and maintaining LLM-powered knowledge bases using specialized AI agents. Raw source material — papers, articles, repos, datasets, images — is ingested, compiled into a structured interlinked markdown wiki, indexed for hybrid retrieval, quality-checked for integrity, and continuously maintained by a team of stationed agents.

The core insight: traditional RAG rediscovers knowledge from scratch on every query. Assistonauts compiles knowledge once, keeps it current, and uses RAG only for routing — finding which compiled articles are relevant — while the LLM reasons over full, structured documents. The result is a knowledge base that compounds over time rather than degrading.

The system is built around six specialized agents (Captain, Scout, Compiler, Curator, Inspector, Explorer) supported by a deterministic knowledge base operating system (the Archivist). Each agent has a defined responsibility boundary, a set of zero-inference toolkit utilities, and uses LLM inference only for judgment calls. The framework deploys first as a CLI for local development and dogfooding, with self-hosted and SaaS deployment surfaces planned for later phases.

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

## Phase 2 — Compiler + Mission Runner

**Goal:** Build the compilation pipeline — the Compiler agent that transforms raw sources into structured wiki articles, and the mission runner that executes and tracks agent work.

**Deliverables:**

1. Wiki schema definition (`_schema.md`) — article templates per type (concept, entity, log, exploration), required frontmatter fields, categorization taxonomy, naming conventions, backlink formatting rules
2. Template engine — apply schema templates to new articles so the LLM fills structured sections rather than generating format from scratch
3. Compiler agent — role implementation with system prompt incorporating expedition scope as editorial lens, compilation pipeline for new sources and diff-oriented recompilation for updates
4. Compiler toolkit — diff generator (structured diff for LLM reasoning), article stats (word count, reading time, source count)
5. Compiler content summary generation — each compilation produces a content summary as a deliverable, optimized for downstream triage by Curator and Explorer
6. Mission runner — single mission execution with YAML audit trail, failure classification (transient vs deterministic), retry logic for transient errors, fail-fast for deterministic errors
7. Mission-level git commits — mission runner commits after each completed mission with mission ID and agent in commit message
8. Compiler contract tests and recorded fixtures — structural validation (valid frontmatter, schema-conformant sections, content summary present, source citations included)
9. CLI: `assistonauts mission run --agent compiler` — execute a single Compiler mission from the command line

**Why this is Phase 2:** The Compiler depends on the base agent class, LLM client, config system, and Scout output from Phase 1. The mission runner is introduced here because Compiler work is the first multi-step agent workflow that needs tracking and audit trails.

**Validation:** Run Scout to ingest a source, then run Compiler via the mission runner to produce a wiki article with valid frontmatter and schema-conformant structure. Git log shows mission-level commits. Contract tests pass. Articles lack cross-referencing (expected — Phase 3 adds it).

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
9. Curator agent — role implementation with system prompt, singleton enforcement, cross-referencing pipeline, proposal generation for structural needs
10. Curator toolkit — backlink scanner (parse links, build graph, identify backlink targets), graph analyzer (connectivity metrics, orphan detection, cluster density)
11. Embedding cache — embedding version tracking, recompute only when content hash changes
12. LLM response cache — SHA-256 prompt hash keying, SQLite backend, configurable TTL, flush per agent/expedition
13. Retroactive cross-referencing — Curator pass over all Phase 1-2 articles to add backlinks and "See also" sections now that the index exists
14. CLI: `assistonauts status` — expedition and knowledge base status overview

**Why this is Phase 3:** The Archivist depends on compiled articles (Phase 2). The Curator depends on the Archivist's retrieval interface. The multi-pass retrieval system needs both the Archivist and a meaningful corpus to validate against. This is the phase where the knowledge base becomes interconnected.

**Validation:** Compile 10+ articles, Archivist indexes them with dual summaries, verify retrieval quality. Curator cross-references a new article — verify multi-pass linking discovers all relevant connections. Verify Phase 1-2 articles are retroactively linked.

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

**Goal:** Build the Captain agent for expedition planning and orchestration, the mission state machine, and the scaling/budget systems.

**Deliverables:**

1. Captain agent — role implementation with two operational modes (planning mode for expedition decomposition, operations mode for routine triage), system prompt with full state visibility
2. Captain toolkit — mission queue manager (priority queue, dependency graph, topological sort), mission ledger (SQLite-backed state persistence), token budget tracker, schedule runner (cron evaluation), status aggregator
3. Iterative planning — plan → execute batch → observe → replan cycle for build phase, with dependency-aware mission sequencing
4. Expedition lifecycle — `expedition.yaml` parsing, build phase orchestration across all agents, phase transition (build → stationed) as explicit human decision
5. Mission state machine — full lifecycle with acceptance criteria, agent-level checklists, status rollup to Captain view, failure classification integration
6. Mission dependency resolution — topological sort, foundational concepts compiled before articles that reference them, cascading mission chains from proposals
7. Deterministic scaling system — concurrent instances for Scout/Compiler/Explorer, Curator singleton enforcement, queue depth triggers, max instances, cooldown. Note: SQLite write concurrency is a known ceiling (see spec)
8. Deterministic budget system — daily token limits, per-agent tracking, warning thresholds, notifications to Captain for station logs
9. CLI: `assistonauts expedition create`, `assistonauts build` — create expeditions and run build phase

**Why this is Phase 5:** The Captain orchestrates all other agents, so it must be built after Scout (Phase 1), Compiler (Phase 2), Archivist/Curator (Phase 3), and Explorer (Phase 4) are functional. The scaling system requires multiple agent types to be available for concurrent execution.

**Validation:** Create an expedition config, Captain produces an iterative plan, executes it end-to-end with proper sequencing. Test scaling with concurrent Compiler instances on a large source batch.

---

## Phase 6 — Inspector + Quality + Review

**Goal:** Build the Inspector agent for quality validation, the audit pipeline, and the human review system.

**Deliverables:**

1. Inspector agent — role implementation with deterministic-scan-first sweep pattern (tools run first, LLM analyzes flagged items only), finding severity levels (critical/warning/info)
2. Inspector toolkit — link checker, orphan detector, staleness scanner, duplicate detector (TF-IDF/simhash), schema validator, source freshness checker (HTTP HEAD/conditional GET)
3. Audit report generation — structured reports in `audits/` with findings, severity, recommended actions, sweep ID tagging
4. Finding-to-fix pipeline — Inspector findings generate Compiler fix missions, auto-fix policy for low-risk findings, human review for high-risk
5. Human review queue — typed review items (inspector_finding, curator_proposal, scout_borderline, exploration_promotion, mission_failure), Captain grouping/summarization, approve/dismiss/defer/inspect actions
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
2. Trigger/event system — event types (new_source, article_update, inspector_finding), trigger matching, event → mission routing via Captain
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
  └─► Phase 2 (Compiler + Mission Runner)
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

4. **Mission retry classification.** Transient failures (API timeouts, rate limits) are retried automatically. Deterministic failures (context overflow, malformed input) are routed to the review queue immediately. Misclassifying a deterministic error as transient wastes tokens; misclassifying a transient error as deterministic creates unnecessary human review. The boundary may need tuning in practice.

5. **Multi-pass retrieval depends on summary quality.** A bad content summary causes the Curator or Explorer to miss relevant connections. This is documented in the spec as "Summary Quality as Infrastructure" — the Compiler's summary generation is core infrastructure, not a nice-to-have.

6. **External dependency: litellm.** The LLM client wraps litellm for provider-agnostic inference. If litellm introduces breaking changes or drops a provider, the wrapper layer isolates the impact. The record/replay mode for testing also reduces dependence on live API availability during development.
