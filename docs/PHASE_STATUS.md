# Phase Status Tracker

> **Current Phase: 3 — Archivist System + Curator + Hybrid RAG**
> Last updated: 2026-04-08, session-2026-04-08-003
> Phase 1 merged to main 2026-04-07
> Phase 2 merged to main 2026-04-08

---

## Phase 1 — Core Infrastructure + Scout

_Goal: Establish the foundation that every subsequent phase builds on — workspace management, config system, base agent class, LLM client, shared toolkit, and the first working agent (Scout)._

- ✅ 2026-04-07, session-2026-04-07-002 — Workspace initialization (`assistonauts init`) — creates the full directory structure, initializes git repo, writes `.gitignore` for derived data
- ✅ 2026-04-07, session-2026-04-07-002 — Config loading system — YAML parser for expedition configs, agent configs, and global settings with validation and sensible defaults
- ✅ 2026-04-07, session-2026-04-07-002 — Base agent class with toolkit integration — `Agent` base class with injectable LLM client, toolkit registration, owned/readable directory enforcement
- ✅ 2026-04-07, session-2026-04-07-002 — LLM client wrapper (litellm) — provider-agnostic inference calls with record/replay mode for test fixtures
- ✅ 2026-04-07, session-2026-04-07-002 — Shared toolkit — structured logger (JSON-lines), config reader, cache interface, file I/O with ownership boundary enforcement
- ✅ 2026-04-07, session-2026-04-07-002 — Content hash cache (manifest) — SHA-256 content tracking in `index/manifest.json`, skip-if-unchanged logic, downstream dependency tracking
- ✅ 2026-04-07, session-2026-04-07-002 — Scout agent — role implementation with system prompt, source ingestion pipeline with frontmatter injection
- ✅ 2026-04-07, session-2026-04-07-002 — Scout toolkit — format converters (markitdown), web clipper, content hasher, deduplication checker (Jaccard shingle similarity)
- ✅ 2026-04-07, session-2026-04-07-002 — Contract test infrastructure — shared conftest fixtures (FakeLLMClient, replay_llm_client, initialized_workspace), fixture directory
- ✅ 2026-04-07, session-2026-04-07-002 — Scout contract tests and recorded fixtures — 6 structural validation tests, recorded fixture file
- ✅ 2026-04-07, session-2026-04-07-002 — CLI entry point — `assistonauts init` and `assistonauts scout ingest <path>` commands via Click + Rich

---

## Phase 2 — Compiler + Mission Runner

_Goal: Build the compilation pipeline — the Compiler agent that transforms raw sources into structured wiki articles, and the mission runner that executes and tracks agent work._

- ✅ 2026-04-07, session-2026-04-07-003 — Wiki schema definition — article types (concept, entity, log, exploration), required frontmatter fields, section templates, naming conventions, backlink formatting rules. Implemented as `models/schema.py`
- ✅ 2026-04-07, session-2026-04-07-003 — Template engine — renders structured markdown scaffolds with YAML frontmatter and section headings with guidance placeholders
- ✅ 2026-04-07, session-2026-04-07-003 — Compiler agent — compilation pipeline for new sources, diff-oriented recompilation for updates, expedition scope as editorial lens in system prompt
- ✅ 2026-04-07, session-2026-04-07-003 — Compiler toolkit — structured diff generator (section-level), article stats (word count, reading time, source count)
- ✅ 2026-04-07, session-2026-04-07-003 — Compiler content summary generation — each compilation produces summary via dedicated LLM prompt, persisted as `.summary.json` alongside article
- ✅ 2026-04-07, session-2026-04-07-003 — Mission runner — single mission execution with YAML audit trail, transient error retry, deterministic error fail-fast, agent resolution by name
- ✅ 2026-04-07, session-2026-04-07-003 — Mission-level git commits — auto_commit option, commit after each completed mission with `[mission-<id>] <agent>: process <title>` format
- ✅ 2026-04-07, session-2026-04-07-003 — Compiler contract tests and recorded fixtures — 16 contract tests validating frontmatter, schema sections, content summary, source citations
- ✅ 2026-04-07, session-2026-04-07-003 — CLI: `assistonauts mission run --agent compiler` — execute single mission with --source, --title, --article-type, --commit options
- ⬜ Multi-source compilation — Compiler accepts multiple source paths, concatenates in order, tracks all source hashes in manifest, lists all sources in frontmatter

---

## Phase 3 — Archivist System + Curator + Hybrid RAG

_Goal: Build the Archivist (deterministic knowledge base operating system), hybrid retrieval, the multi-pass retrieval system, and the Curator agent for cross-referencing._

- ✅ 2026-04-08, session-2026-04-08-003 — Archivist system core — main `Archivist` class with service interface (`index()`, `search()`, `reindex_batch()`, `get_staleness()`, `get_downstream()`, `get_stale_articles()`), not an agent — no LLM inference
- ✅ 2026-04-08, session-2026-04-08-003 — Embedding generation and storage — `EmbeddingClient` ABC with `LiteLLMEmbeddingClient`, chunking, batching, storage in `index/assistonauts.db` (sqlite-vec)
- ✅ 2026-04-08, session-2026-04-08-003 — FTS indexing — SQLite FTS5 insert/update/delete for keyword-based retrieval with query sanitization
- ✅ 2026-04-08, session-2026-04-08-003 — Hybrid retrieval — vector similarity + FTS keyword search, reciprocal rank fusion reranking, configurable relevance floor, no arbitrary result cap
- ✅ 2026-04-08, session-2026-04-08-003 — Dual summary storage — retrieval summaries (deterministic keyword extraction) and content summaries in `summaries` table in `index/assistonauts.db` (SQLite, not JSONL — collocated with other index data)
- ✅ 2026-04-08, session-2026-04-08-003 — Manifest management — full lineage tracking, staleness graphs via `get_stale_articles()`, embedding version tracking via `embedding_hash` column
- ✅ 2026-04-08, session-2026-04-08-003 — Multi-pass retrieval system — shared module (`rag/multi_pass.py`) with Pass 1 (broad scan, zero inference), Pass 2 (triage on summaries, cheap LLM inference), Pass 3 (deep read, targeted inference), Pass 4 (weak match resolution)
- ✅ 2026-04-08, session-2026-04-08-003 — Short-circuit mode — bypass multi-pass for small knowledge bases (below configurable article/word count threshold), load all articles directly
- ✅ 2026-04-08, session-2026-04-08-003 — Curator agent — role implementation with system prompt, singleton enforcement (class-level lock), cross-referencing pipeline, proposal generation for structural needs (orphan detection, low connectivity)
- ✅ 2026-04-08, session-2026-04-08-003 — Curator toolkit — backlink scanner (parse wiki-links, build graph, identify backlink targets), graph analyzer (connectivity metrics, orphan detection, density)
- ✅ 2026-04-08, session-2026-04-08-003 — Embedding cache — embedding version tracking via `embedding_hash`, recompute only when content hash changes
- ✅ 2026-04-08, session-2026-04-08-003 — LLM response cache — SHA-256 prompt hash keying, SQLite backend, configurable TTL, flush per agent/expedition, max_size_mb enforcement, integrated into LLMClient
- ✅ 2026-04-08, session-2026-04-08-003 — Retroactive cross-referencing — `retroactive_cross_reference()` on CuratorAgent, batch pass over all indexed articles
- ✅ 2026-04-08, session-2026-04-08-003 — CLI: `assistonauts status` — knowledge base status overview with article counts, word count, stale detection
- ✅ 2026-04-08, session-2026-04-08-003 — Image ingestion in Scout — vision model support (Gemma 4 via litellm) for image files (.png, .jpg, .jpeg, .gif, .webp), multimodal LLM text extraction via `convert_image()`, auto-detection in Scout.ingest()
- ✅ 2026-04-08, session-2026-04-08-003 — CLI: `assistonauts index` — index all wiki articles into the Archivist (FTS + metadata), `--reindex` flag for force reindexing
- ✅ 2026-04-08, session-2026-04-08-003 — CLI: `assistonauts curate` — structural proposals via `--proposals` flag (orphans, low connectivity), cross-referencing placeholder for LLM-dependent mode
- ⬜ Batch ingestion CLI — `scout ingest` accepts multiple file arguments or globs

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
