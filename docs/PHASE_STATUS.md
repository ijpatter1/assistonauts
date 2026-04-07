# Phase Status Tracker

> **Current Phase: 1 — Core Infrastructure + Scout**
> Last updated: 2026-04-07, session-2026-04-07-001

---

## Phase 1 — Core Infrastructure + Scout

_Goal: Establish the foundation that every subsequent phase builds on — workspace management, config system, base agent class, LLM client, shared toolkit, and the first working agent (Scout)._

- ⬜ Workspace initialization (`assistonauts init`) — creates the full directory structure (`raw/`, `wiki/`, `index/`, `audits/`, `expeditions/`, `station-logs/`, `.assistonauts/`), initializes git repo, writes `.gitignore` for derived data
- ⬜ Config loading system — YAML parser for expedition configs, agent configs, and global settings with validation and sensible defaults
- ⬜ Base agent class with toolkit integration — `Agent` base class with injectable LLM client, toolkit registration, owned/readable directory enforcement, and structured logging. Designed for testability (see Testing Strategy in spec)
- ⬜ LLM client wrapper (litellm) — provider-agnostic inference calls with record/replay mode for test fixtures, configurable role-to-provider mapping
- ⬜ Shared toolkit — logger (structured, to mission log files), config reader, cache interface, file I/O with ownership boundary enforcement
- ⬜ Content hash cache (manifest) — SHA-256 content tracking in `index/manifest.json`, skip-if-unchanged logic, downstream dependency tracking
- ⬜ Scout agent — role implementation with system prompt, relevance filtering (keyword match + optional LLM check), source ingestion pipeline
- ⬜ Scout toolkit — format converters (PDF/HTML/DOCX to markdown via markitdown), web clipper (fetch + extract + download assets), content hasher, deduplication checker (simhash/minhash)
- ⬜ Contract test infrastructure — pytest fixtures, LLM client replay mode integration, assertion helpers for agent output structure validation
- ⬜ Scout contract tests and recorded fixtures — structural validation of Scout output (valid markdown, assets referenced correctly, frontmatter present)
- ⬜ CLI entry point — `assistonauts init` and `assistonauts scout ingest <path-or-url>` commands via Click + Rich

---

## Phase 2 — Compiler + Mission Runner

_Goal: Build the compilation pipeline — the Compiler agent that transforms raw sources into structured wiki articles, and the mission runner that executes and tracks agent work._

- ⬜ Wiki schema definition (`_schema.md`) — article templates per type (concept, entity, log, exploration), required frontmatter fields, categorization taxonomy, naming conventions, backlink formatting rules
- ⬜ Template engine — apply schema templates to new articles so the LLM fills structured sections rather than generating format from scratch
- ⬜ Compiler agent — role implementation with system prompt incorporating expedition scope as editorial lens, compilation pipeline for new sources and diff-oriented recompilation for updates
- ⬜ Compiler toolkit — diff generator (structured diff for LLM reasoning), article stats (word count, reading time, source count)
- ⬜ Compiler content summary generation — each compilation produces a content summary as a deliverable, optimized for downstream triage by Curator and Explorer
- ⬜ Mission runner — single mission execution with YAML audit trail, failure classification (transient vs deterministic), retry logic for transient errors, fail-fast for deterministic errors
- ⬜ Mission-level git commits — mission runner commits after each completed mission with mission ID and agent in commit message
- ⬜ Compiler contract tests and recorded fixtures — structural validation (valid frontmatter, schema-conformant sections, content summary present, source citations included)
- ⬜ CLI: `assistonauts mission run --agent compiler` — execute a single Compiler mission from the command line

---

## Phase 3 — Archivist System + Curator + Hybrid RAG

_Goal: Build the Archivist (deterministic knowledge base operating system), hybrid retrieval, the multi-pass retrieval system, and the Curator agent for cross-referencing._

- ⬜ Archivist system core — main `Archivist` class with service interface (`index()`, `search()`, `reindex_batch()`, `get_staleness()`, `get_downstream()`), not an agent — no LLM inference
- ⬜ Embedding generation and storage — embedding model API calls via litellm, chunking, batching, storage in `index/assistonauts.db` (sqlite-vec)
- ⬜ FTS indexing — SQLite FTS5 insert/update/delete for keyword-based retrieval
- ⬜ Hybrid retrieval — vector similarity + FTS keyword search, reciprocal rank fusion reranking, configurable relevance floor, no arbitrary result cap
- ⬜ Dual summary storage — retrieval summaries (deterministic keyword extraction) and content summaries (received from Compiler) in `index/summaries.jsonl`
- ⬜ Manifest management — full lineage tracking, staleness graphs, embedding version tracking, summary staleness detection
- ⬜ Multi-pass retrieval system — shared module (`rag/multi_pass.py`) with Pass 1 (broad scan, zero inference), Pass 2 (triage on summaries, cheap inference), Pass 3 (deep read, targeted inference), Pass 4 (weak match resolution)
- ⬜ Short-circuit mode — bypass multi-pass for small knowledge bases (below configurable article/word count threshold), load all articles directly
- ⬜ Curator agent — role implementation with system prompt, singleton enforcement, cross-referencing pipeline, proposal generation for structural needs
- ⬜ Curator toolkit — backlink scanner (parse links, build graph, identify backlink targets), graph analyzer (connectivity metrics, orphan detection, cluster density)
- ⬜ Embedding cache — embedding version tracking, recompute only when content hash changes
- ⬜ LLM response cache — SHA-256 prompt hash keying, SQLite backend, configurable TTL, flush per agent/expedition
- ⬜ Retroactive cross-referencing — Curator pass over all Phase 1-2 articles to add backlinks and "See also" sections now that the index exists
- ⬜ CLI: `assistonauts status` — expedition and knowledge base status overview

---

## Phase 4 — Explorer + Interactive Mode

_Goal: Build the Explorer agent for query synthesis and an interactive REPL for human-driven Q&A against the knowledge base._

- ⬜ Explorer agent — role implementation with system prompt, query flow via multi-pass retrieval, answer synthesis with citations to specific wiki articles
- ⬜ Explorer toolkit — citation formatter, context budget calculator (recommend include/exclude to fit context window), output renderer (markdown, Marp slides, matplotlib charts)
- ⬜ Exploration filing — save valuable answers to `wiki/explorations/` with proper frontmatter, indexed by Archivist but not cross-linked into main wiki until promoted
- ⬜ Interactive REPL — Click-based CLI session for human-driven Q&A, conversational flow, optional answer filing
- ⬜ Explorer contract tests and recorded fixtures — structural validation (citations to real articles, answer format, context budget respected)
- ⬜ CLI: `assistonauts explore <expedition-name>` — launch interactive Explorer session

---

## Phase 5 — Captain + Expedition Orchestration

_Goal: Build the Captain agent for expedition planning and orchestration, the mission state machine, and the scaling/budget systems._

- ⬜ Captain agent — role implementation with two operational modes (planning mode for expedition decomposition, operations mode for routine triage), system prompt with full state visibility
- ⬜ Captain toolkit — mission queue manager (priority queue, dependency graph, topological sort), mission ledger (SQLite-backed state persistence), token budget tracker, schedule runner (cron evaluation), status aggregator
- ⬜ Iterative planning — plan → execute batch → observe → replan cycle for build phase, with dependency-aware mission sequencing
- ⬜ Expedition lifecycle — `expedition.yaml` parsing, build phase orchestration across all agents, phase transition (build → stationed) as explicit human decision
- ⬜ Mission state machine — full lifecycle with acceptance criteria, agent-level checklists, status rollup to Captain view, failure classification integration
- ⬜ Mission dependency resolution — topological sort, foundational concepts compiled before articles that reference them, cascading mission chains from proposals
- ⬜ Deterministic scaling system — concurrent instances for Scout/Compiler/Explorer, Curator singleton enforcement, queue depth triggers, max instances, cooldown. Note: SQLite write concurrency is a known ceiling (see spec)
- ⬜ Deterministic budget system — daily token limits, per-agent tracking, warning thresholds, notifications to Captain for station logs
- ⬜ CLI: `assistonauts expedition create`, `assistonauts build` — create expeditions and run build phase

---

## Phase 6 — Inspector + Quality + Review

_Goal: Build the Inspector agent for quality validation, the audit pipeline, and the human review system._

- ⬜ Inspector agent — role implementation with deterministic-scan-first sweep pattern (tools run first, LLM analyzes flagged items only), finding severity levels (critical/warning/info)
- ⬜ Inspector toolkit — link checker, orphan detector, staleness scanner, duplicate detector (TF-IDF/simhash), schema validator, source freshness checker (HTTP HEAD/conditional GET)
- ⬜ Audit report generation — structured reports in `audits/` with findings, severity, recommended actions, sweep ID tagging
- ⬜ Finding-to-fix pipeline — Inspector findings generate Compiler fix missions, auto-fix policy for low-risk findings, human review for high-risk
- ⬜ Human review queue — typed review items (inspector_finding, curator_proposal, scout_borderline, exploration_promotion, mission_failure), Captain grouping/summarization, approve/dismiss/defer/inspect actions
- ⬜ Review storage and CLI — `expeditions/<n>/review/` YAML files, `assistonauts review` command with categorized display, drill-down, stale review escalation
- ⬜ Exploration promotion pipeline — Inspector technical quality check → human approval → standard ingestion flow (Compiler recompiles, Curator links)
- ⬜ Summary quality checks — Inspector validates Compiler-generated content summaries, flags stale/vague/missing summaries. First sweep should anticipate a batch of findings from Phases 2-5
- ⬜ Cycle guard — Inspector skips articles whose only changes since last sweep are finding-resolution commits, Curator backlink additions do not trigger re-audit

---

## Phase 7 — Stationed Mode

_Goal: Enable continuous, autonomous operation — agents watch for changes, respond to events, and maintain the knowledge base on a schedule._

- ⬜ Watch system — `watchdog` for local directories, RSS feed parser (`feedparser`), GitHub API poller for repo events, web page change detection (HTTP conditional GET + content diff)
- ⬜ Trigger/event system — event types (new_source, article_update, inspector_finding), trigger matching, event → mission routing via Captain
- ⬜ Scheduled execution — cron expression evaluation for Scout watch intervals, Inspector sweep schedule, station log generation
- ⬜ Station log generation — weekly Captain reports with knowledge base health metrics (article count, word count, orphan rate, cross-referencing density, contradiction count, summary freshness, cache hit rates, token usage by agent)
- ⬜ Stale review item escalation — Captain tracks pending review age, escalates items older than configurable threshold in station logs
- ⬜ Cycle guards — Inspector sweep ID tagging prevents re-auditing just-fixed articles, Curator link-section edits distinguished from content edits
- ⬜ Pause/resume support — `assistonauts pause` halts all agent activity, `assistonauts resume` restarts from current state
- ⬜ CLI: `assistonauts station`, `assistonauts log`, `assistonauts pause`, `assistonauts resume`
