# Assistonauts

## Product Requirements Document

---

## Overview

Assistonauts is a framework for building and maintaining LLM-powered knowledge bases using specialized AI agents. Raw source material — papers, articles, repos, datasets, images — is ingested, compiled into a structured interlinked markdown wiki, indexed for hybrid retrieval, quality-checked for integrity, and continuously maintained by a team of stationed agents.

The core insight: traditional RAG rediscovers knowledge from scratch on every query. Assistonauts compiles knowledge once, keeps it current, and uses RAG only for routing — finding which compiled articles are relevant — while the LLM reasons over full, structured documents.

### Deployment Surfaces

- **CLI** — local development, power users, dogfooding environment
- **Self-hosted open source** — enterprise customers who won't send data to third parties
- **SaaS** — managed platform for smaller teams

### Commercial Model

Begins as a consulting service (Patterson Consulting builds knowledge bases for clients), transitions to product once multiple expedition case studies validate the model. The build phase is a consulting engagement with a deliverable. Stationing agents is a subscription.

---

## Core Concepts

### Expedition

A large-scale knowledge base initiative with a defined goal, a team of agents, and two phases.

**Build phase:** Initial ingestion, compilation, indexing, and quality validation of the knowledge base. Ends with human review and approval that the base is ready for ongoing maintenance.

**Stationed phase:** Agents remain at the knowledge base permanently. Scouts watch for new sources, the Inspector runs scheduled integrity sweeps, the Compiler reactively updates articles, the Curator maintains cross-references, and the Archivist system keeps the index current. The transition from build to stationed is an explicit human decision.

An expedition is defined by a YAML configuration. The `scope` block is propagated to the Scout (for relevance filtering), the Compiler (as an editorial lens in its system prompt), and the Curator (to prioritize domain-relevant connections over tangential ones):

```yaml
expedition:
  name: autotrader-research
  description: "Research knowledge base for BTC/USD prediction system"
  phase: build # build | stationed

  scope:
    description: >
      Machine learning approaches to cryptocurrency price prediction,
      including feature engineering, regime detection, walk-forward
      validation, and capital efficiency optimization.
    keywords: [ML, trading, BTC, regime detection, walk-forward, features]

  sources:
    local:
      - path: ~/research/experiments/
        pattern: "*.md"
        watch: true
      - path: ~/research/papers/
        pattern: "*.pdf"
        watch: true
    rss:
      - url: https://arxiv.org/rss/cs.LG
        filter_relevance: true
    github:
      - repo: owner/repo
        events: [release, push]
    web:
      - url: https://alternative.me/crypto/fear-and-greed-index/
        schedule: "0 0 * * *"
        detect: content_change

  stationed:
    schedule:
      scout_watch: "*/6 * * *" # check watched sources every 6 hours
      inspector_sweep: "0 0 * * 0" # full integrity sweep weekly
      station_log: "0 8 * * 1" # weekly station log Monday 8am
    triggers:
      on_new_source: [compiler]
      on_article_update: [curator]
      on_inspector_finding:
        critical: [compiler] # immediate fix
        warning: review_queue # human decides
        info: log_only # noted in station log
    resources:
      daily_token_budget: 100000 # also referenced in scaling.budget.daily_token_limit
      max_concurrent_missions: 3
    reporting:
      station_log: weekly
```

### Mission

A scoped unit of work assigned to a specific agent. Has defined inputs, acceptance criteria, and output artifacts. Missions are created by the Captain — either from the expedition plan during the build phase or reactively during the stationed phase.

**Acceptance criteria and checklists:**

The Captain produces mission-level acceptance criteria during planning — the top-down definition of "done." When an agent begins a mission, it refines those criteria into a granular operational checklist reflecting the specific steps it needs to execute. The agent checks off items as it works. Both levels roll up to the Captain's mission status view:

- **Captain-level criteria** — strategic: "Concept article on spectral features written, content summary generated, ready for Curator cross-referencing"
- **Agent-level checklist** — operational: "Read source A, read source B, compile article, apply schema template, generate content summary, update frontmatter"

Mission completion is agent-declared against its own checklist, verified by the Captain against the mission-level criteria. The Inspector catches quality issues after the fact during its sweeps.

```yaml
mission:
  id: mission-0042
  agent: compiler
  type: compile_article
  status: pending # pending | running | completed | failed | stale
  priority: high
  inputs:
    sources:
      - raw/papers/fft-analysis.md
      - raw/papers/spectral-entropy.md
  acceptance_criteria:
    - "Concept article on spectral features written"
    - "Content summary generated for Archivist system"
  checklist: [] # agent populates with granular steps at mission start
  created_by: captain
  created_at: 2026-04-05T12:00:00Z
```

**Mission state persistence:**

Mission status is persisted in a SQLite mission ledger (atomic writes, deterministic reads). The YAML mission files serve as the human-readable audit trail. The ledger is the source of truth for the Captain's toolkit; the YAML files are the record of what happened and why.

Mission states:

```
pending → running → completed
                ↓
             failed (transient) → pending (retry, max 3)
             failed (deterministic) → review queue (no retry)
         completed → stale (when inputs change)
```

**Failure classification:**

The mission runner classifies failures into two categories to avoid wasting tokens on unrecoverable errors:

- **Transient** — API timeouts, rate limits, 5xx errors, network failures. These are retried automatically (max 3 attempts with exponential backoff). Most transient failures resolve on retry.
- **Deterministic** — context window overflow, malformed input (e.g., corrupted PDF conversion), schema validation failure, agent output that fails structural checks. These will produce the same failure on retry. The mission is marked `failed` immediately and routed to the review queue with the error category and details so the human can diagnose and fix the root cause (e.g., split the source, re-convert the PDF, fix the schema).

The mission YAML records the failure type, error message, and retry count for audit trail purposes:

```yaml
failure:
  type: deterministic # transient | deterministic
  error: "Context window exceeded: 210K tokens (limit: 200K)"
  retries: 0 # 0 for deterministic, 1-3 for transient
  failed_at: 2026-04-05T12:05:00Z
```

---

## Agents

Six specialized agents, each with a defined responsibility boundary, operating through missions assigned by the Captain. Agents exercise judgment via LLM inference — they reason, decide, and produce artifacts.

The agents are supported by the Archivist, a deterministic knowledge base operating system documented separately below.

### Captain

Leads the expedition. The single coordination point between the human and the agent team.

**Responsibilities:**

- Reads the expedition definition and decomposes it into a sequenced mission plan
- Understands dependencies between missions (foundational concepts must be compiled before articles that reference them)
- Assigns missions to the appropriate agents and manages the execution queue
- Triages events during the stationed phase — decides urgency, priority, and sequencing
- Manages the human review queue — surfaces decisions that need approval, summarizes what needs attention
- Tracks resource usage (token spend, cache hit rates, mission throughput)
- Produces station logs and expedition status reports

**Operational characteristics:**

- Should run on a frontier model — the Captain's planning, sequencing, and triage decisions are the highest-judgment work in the system. A bad plan wastes every downstream agent's budget. The Captain makes fewer LLM calls than the Compiler or Explorer, so the cost premium of frontier inference is negligible compared to the cost of poor strategic decisions.
- Reads status, manifests, and summaries rather than full articles — its inputs are lightweight even though its reasoning is sophisticated.
- The only agent with visibility into the full state of the knowledge base and all agent activity.
- Two operational modes:
  - **Planning mode** — expedition decomposition, mission sequencing, structural decisions. Infrequent but high-stakes. Triggered at expedition start and on significant human directives.
  - **Operations mode** — routine triage during stationed phase, status aggregation, station log generation. More frequent, leans heavily on deterministic toolkit for mechanics, with the LLM making judgment calls on top.

**Does not:**

- Write wiki articles (Compiler's job)
- Process raw sources (Scout's job)
- Manage the search index (Archivist system)
- Edit files owned by other agents

**Toolkit (deterministic, zero-inference):**

- **Mission queue manager** — priority queue operations, dependency graph resolution, topological sort for sequencing
- **Mission ledger** — SQLite-backed mission state persistence. Atomic reads and writes. Source of truth for all mission status. YAML mission files are written as the human-readable audit trail.
- **Token budget tracker** — running tally of spend by agent and expedition, alerts at configurable thresholds
- **Schedule runner** — cron expression evaluation, trigger matching against event types
- **Status aggregator** — reads mission ledger and agent statuses, produces structured summaries the Captain's LLM can reason over quickly. Rolls up agent checklists into mission-level acceptance criteria views.

**Interaction model:**

The human gives directives to the Captain. The Captain translates them into missions. Examples:

- Human: "Start the expedition" → Captain produces a build plan with sequenced missions
- Human: "Prioritize the new papers on regime detection" → Captain reprioritizes the Compiler's queue
- Human: "What changed this week?" → Captain produces a station log summary
- Human: "I disagree with this Inspector finding, dismiss it" → Captain marks finding dismissed

### Scout

Recon and ingestion. Brings raw source material into the knowledge base.

**Responsibilities:**

- Converts web articles, PDFs, repos, images, and other formats into markdown in `raw/`
- Downloads associated assets (images, diagrams) to `raw/assets/` and updates markdown references
- Performs lightweight relevance filtering against the expedition scope before ingesting
- When stationed, watches configured sources (directories, RSS feeds, GitHub repos, web pages) for new material
- Reports new ingestions to the Captain for downstream mission creation

**Owns:** `raw/`

**Toolkit (deterministic, zero-inference):**

- **Format converters** — PDF to markdown, HTML to markdown, EPUB to markdown. Deterministic conversion, no LLM needed. The converter implementation is pluggable (default: `markitdown`) — the PDF-to-markdown space is evolving rapidly and the system should not be locked to a specific library
- **Web clipper** — fetch URL, extract content, download associated assets (images, diagrams), save as markdown with local asset references
- **File watcher** — `watchdog` for local directories, RSS parser for feeds, GitHub API poller for repo events
- **Content hasher** — SHA-256 the file, check against manifest, skip if unchanged
- **Deduplication checker** — fuzzy hash (simhash or minhash) to catch near-duplicate sources before they consume Compiler tokens

**Relevance filtering:**

When pointed at a high-volume source like an RSS feed, the Scout evaluates each item against the expedition's scope definition and keywords. Two-stage filtering:

1. **Keyword match (deterministic, zero-inference)** — fast first pass comparing item title and abstract against `scope.keywords`. Items with zero keyword overlap are rejected immediately.
2. **LLM relevance check (optional, cheap inference)** — borderline items that pass keyword match but score below the threshold get a lightweight LLM judgment call against the scope description. This catches items that are semantically relevant but use different terminology.

Items below the relevance threshold are logged but not ingested. This prevents burning Compiler tokens on irrelevant material. Borderline rejections are surfaced to the Captain's review queue so the human can override.

```yaml
scout:
  relevance_threshold: 0.6 # 0-1, how strictly to filter
  borderline_range: [0.4, 0.6] # items in this range get LLM check
  log_rejected: true # keep a record of what was filtered out
```

This mechanism is subject to tuning in practice — the threshold and borderline range will likely need adjustment per expedition based on source volume and domain specificity.

### Compiler

Synthesis and article writing. Transforms raw sources into structured wiki content.

**Responsibilities:**

- Reads raw sources and produces wiki articles — concept pages, entity pages, summaries
- Generates a content summary for each compiled article as a deliverable (handed to the Archivist system for storage — this avoids needing LLM inference in the indexing layer)
- During build phase, processes the backlog of raw sources in the sequence determined by the Captain
- During stationed phase, reactively updates articles when sources change or Inspector findings require fixes
- Uses diff-oriented recompilation when updating existing articles — receives the current article, the changed source, and updates accordingly rather than rewriting from scratch

**Owns:** `wiki/` article content (except `_index.md` and `explorations/`). Note: the Curator has write access to backlink sections within articles the Compiler owns — see Curator ownership boundary for the distinction between article content and inter-article links.

**Toolkit (deterministic, zero-inference):**

- **Diff generator** — given old and new versions of a source, produce a structured diff the LLM can reason over instead of comparing full documents
- **Template engine** — apply wiki schema templates to new articles so the LLM fills in structured sections rather than generating format from scratch
- **Article stats** — word count, reading time, source count per article. Feeds station logs without inference

**Does not:**

- Create or maintain backlinks (Curator's job)
- Propose structural changes (Curator's job)
- Maintain the master index or manifest (Archivist system)
- Edit files in `raw/` (Scout's job)

**Compilation approach:**

The Compiler receives the expedition's scope definition (description and keywords) as part of its system prompt. This ensures articles stay on-topic — if a source about NLP is ingested into an ML trading expedition, the Compiler focuses on the trading-relevant aspects, not the NLP methodology. The scope acts as an editorial lens across all compilation work.

For new sources, the Compiler receives:

- The expedition scope (via system prompt)
- The raw source document
- The current wiki schema and conventions

For updates to existing articles, the Compiler receives:

- The current article content
- The changed source material with a diff summary (via diff generator tool)
- Any Inspector findings related to the article

**Compiler output per mission:**

Each compilation mission produces:

1. The wiki article (written to `wiki/`)
2. A content summary (handed to the Archivist system for `summaries.jsonl` — generated while the source is fresh in context, essentially free)

After the Compiler completes, the Archivist system automatically indexes the article. In stationed mode, the Captain then schedules a Curator mission to cross-reference the new article. During build phase, the Captain batches Curator work until the compilation corpus is complete.

### Curator

Cross-referencing, linking, and structural stewardship. The agent responsible for how articles relate to each other and how the knowledge base is organized as a whole.

**Responsibilities:**

- Runs multi-pass retrieval (via the Archivist system) to discover connections for new or updated articles
- Creates and maintains backlinks between related articles
- Proposes new categories, concept pages, and structural reorganization (see Proposals below)
- Maintains the coherence of the knowledge graph — ensures the wiki reads as an interconnected whole, not a collection of isolated articles
- In stationed mode, runs after the Compiler finishes an article — takes the Compiler's output and weaves it into the existing fabric. During build phase, the Captain schedules Curator cross-referencing after the compilation corpus is complete (see Build Phase iteration 3).

**Proposals:**

During cross-referencing, the Curator may identify structural needs — a concept referenced by multiple articles with no dedicated page, a category that should exist, or a reorganization that would improve navigability. These are emitted as proposal artifacts. The Captain picks up proposals and routes them to the human review queue. Approved proposals generate a dependency chain of missions:

1. Compiler mission to write the new concept page or restructured articles
2. Archivist system indexes the new content
3. Curator mission to link the new content into the existing wiki

The Captain sequences these with correct dependencies. This cascading work reinforces the need for the Captain's frontier-model planning to correctly prioritize the resulting workload.

**Owns:** Backlink sections within `wiki/` articles. The ownership boundary between Compiler and Curator is:

- **Compiler** writes forward — inline references to other articles as part of the article's narrative ("As discussed in [regime detection](concepts/regime-detection.md)...") are article content owned by the Compiler.
- **Curator** weaves backward — the dedicated "Related" and "See also" sections at the end of articles, plus backlinks added FROM existing articles TO a new article. The Curator reads the new article and updates other articles to reference it.

**Toolkit (deterministic, zero-inference):**

- **Backlink scanner** — parse all wiki articles for internal links, build the link graph, identify candidate backlink targets. Graph traversal is deterministic; the LLM decides which suggested links are meaningful
- **Graph analyzer** — compute connectivity metrics (orphaned articles, cluster density, cross-referencing coverage). Feeds station log health metrics

**Operational characteristics:**

- Singleton — the Curator needs a consistent view of the knowledge graph. Two Curators linking simultaneously would create conflicting edits. This serialization point also eliminates the concurrent-backlink-write problem entirely; all cross-referencing funnels through one agent.
- Frontier model — deciding what connects to what requires broad understanding of the knowledge base's concept landscape.
- Receives content summaries from the Archivist system to make linking decisions efficiently (via multi-pass retrieval).

**Article linking:** The Curator uses the Multi-Pass Retrieval System (see dedicated section below) to exhaustively discover and create connections for each new or updated article. This ensures no relevant link is missed while keeping inference costs proportional to actual relevance, not corpus size.

```yaml
curator:
  linking:
    relevance_floor: 0.3 # minimum similarity score, no cap on count
    summary_type: content # use content summaries for triage
    deep_read_batch_size: 4 # articles per inference call in pass 3
    weak_link_style: see_also # how to format tangential references
```

### Inspector

Quality and integrity. Ensures the knowledge base remains consistent, complete, and accurate over time.

**Responsibilities:**

- Finds contradictions between articles (Article A says X, Article B says Y)
- Identifies gaps — topics referenced but never covered, missing backlinks
- Detects stale references — sources that have changed since the article was compiled
- Validates source accessibility — checks that referenced sources still exist, web sources haven't gone offline, papers haven't been retracted
- Finds broken internal links between wiki articles
- Performs technical quality checks on Explorer output pending wiki promotion (accuracy, citation validity, consistency with existing articles — not relevance judgment)
- Produces audit reports in `audits/` with findings, severity, and recommended actions
- During stationed phase, runs scheduled sweeps and triggered checks

**Owns:** `audits/`

**Toolkit (deterministic, zero-inference):**

- **Link checker** — crawl all internal wiki links, verify targets exist. HTTP HEAD requests for external URLs. Zero inference
- **Orphan detector** — graph analysis on the backlink structure, find articles with no inbound links
- **Staleness scanner** — compare source content hashes against manifest timestamps, flag articles where the source is newer than the compiled version
- **Duplicate detector** — TF-IDF or simhash similarity across all articles, flag pairs above a threshold for potential merge
- **Schema validator** — check articles against wiki schema templates, find missing required sections or malformed frontmatter
- **Source freshness checker** — for web sources, HTTP HEAD or conditional GET to detect changes without full re-download. Detect retracted papers, moved URLs, dead links

The Inspector's sweep pattern: run all deterministic tools first, producing a structured findings report. Then the LLM reviews the findings, assesses severity, identifies semantic contradictions that tools cannot catch (e.g. "Article A says X outperforms Y but Article B says Y outperforms X"), and writes the audit report. This reduces a full sweep from a massive inference job to a cheap deterministic scan with targeted LLM analysis on flagged items only.

**Does not:**

- Edit wiki articles directly — separation of duties. The Inspector produces findings, findings generate Compiler missions for fixes. This creates an audit trail: Inspector found X → Compiler fixed X → diff recorded.

**Finding severity levels:**

- `critical` — direct contradiction between articles, requires immediate Compiler attention
- `warning` — stale data, missing links, gaps in coverage
- `info` — structural gap suggestions (e.g., "concept X mentioned in 5 articles but has no dedicated page"). Note: the Inspector identifies gaps via metadata patterns and graph analysis, while the Curator identifies semantic connections via content understanding during cross-referencing. The Inspector works from structural signals; the Curator reads and reasons about meaning. Both may surface proposals for new articles, but through different mechanisms.

**Auto-fix policy:**

Low-risk findings (broken links, simple stale references) can be configured to auto-generate Compiler missions without human approval. High-risk findings (contradictions, structural changes) go to the Captain's review queue.

```yaml
inspector:
  auto_fix:
    broken_links: true # auto-generates Compiler mission to remove or update the dead reference
    stale_references: true # auto-generates Compiler mission to recompile from updated source
    contradictions: false # always flag for human review
    gaps: false
```

### Explorer

Research and knowledge synthesis. The agent that turns the knowledge base into actionable intelligence.

**Responsibilities:**

- Handles queries against the knowledge base — uses the Archivist system's retrieval interface to find relevant articles, loads full articles into context, synthesizes answers
- Can produce output in multiple formats: markdown articles, comparison tables, visualizations
- Files valuable answers back into `wiki/explorations/` to compound knowledge
- Can run autonomous research missions assigned by the Captain ("explore the relationship between X and Y across all experiments and write a synthesis article")
- Can operate in interactive mode as a REPL session for human-driven Q&A

**Owns:** `wiki/explorations/`

**Toolkit (deterministic, zero-inference):**

- **Citation formatter** — given article references from the retrieval step, format them consistently without LLM
- **Context budget calculator** — given a query and N candidate articles, calculate total tokens if loaded, recommend which to include/exclude to stay within the model's context window
- **Output renderer** — convert the LLM's markdown output to Marp slides, matplotlib charts, or other visualization formats. Deterministic rendering

**Two operational modes:**

- **Mission mode** — autonomous research assigned by the Captain, produces artifacts, completes
- **Interactive mode** — human-driven Q&A session via the CLI, conversational, may or may not file answers

**Query flow:**

The Explorer uses the Multi-Pass Retrieval System (see dedicated section below) — the same system used by the Curator for article linking. This shared approach ensures consistent, exhaustive retrieval across both agents while keeping inference costs proportional to relevance:

1. Explorer receives query (from human or Captain)
2. Pass 1: Archivist system returns all candidates above relevance floor (zero inference)
3. Pass 2: Explorer's LLM triages candidates using content summaries only (cheap inference)
4. Pass 3: Explorer loads full text of strong-match articles and synthesizes answer (targeted inference)
5. Explorer produces answer with citations to specific wiki articles
6. Optionally files the answer as an exploration article in `wiki/explorations/`

**Exploration Pipeline:**

Explorer output is treated analogously to Scout output — it is raw material that must go through a quality gate before integration into the wiki proper. This prevents unvetted content from polluting the wiki's integrity.

```
Explorer produces exploration →
  Inspector performs technical quality check (accuracy, citation validity,
    consistency with existing articles — not relevance judgment) →
  Human approves via review queue →
  Approved exploration moves into the standard ingestion flow
    (treated like any raw source: Compiler compiles, Curator links) →
  Rejected/archived: stays in explorations/ as reference, not wiki-integrated
```

Explorations in `wiki/explorations/` are explicitly provisional. They are indexed by the Archivist system and available for queries, but they are not cross-linked into the main wiki structure until promoted through the pipeline. This maintains the guarantee that everything in `wiki/concepts/` and `wiki/entities/` has been through the full compilation, curation, and inspection process.

---

## Archivist — Knowledge Base Operating System

The Archivist is not an agent — it exercises no judgment and makes no LLM inference calls. It is the deterministic operating system of the knowledge base: the indexing engine, retrieval interface, and manifest that all six agents rely on. Think of it as the ship's computer — always running, always responsive, called directly by agents and the mission runner rather than receiving missions through the Captain.

### Responsibilities

- Generates and maintains embeddings for all wiki articles in the vector index
- Maintains FTS (full-text search) entries for keyword-based retrieval
- Maintains dual article summaries (see below)
- Maintains the master index (`wiki/_index.md`) and the manifest (`index/manifest.json`)
- Tracks content hashes, processing timestamps, embedding versions, and summary staleness
- Automatically indexes articles when the Compiler produces or updates them
- Provides the retrieval interface used by the Multi-Pass Retrieval System — accepts a query, returns ranked article references with summaries and file paths

### Owns

`index/`, `wiki/_index.md`

### Interface

Other agents call the Archivist directly as a service, not through the mission system:

```python
# After Compiler finishes an article
archivist.index(article_path, content_summary)

# Curator or Explorer performing multi-pass retrieval
results = archivist.search(query, relevance_floor=0.3)

# Batch reindexing
archivist.reindex_batch(article_paths)

# Manifest queries
archivist.get_staleness(article_path)
archivist.get_downstream(source_path)
```

### Components

- **Embedding generator** — calls the embedding model API; chunking, batching, and storage are deterministic code
- **FTS indexer** — SQLite FTS5 insert/update/delete operations
- **Vector search** — `sqlite-vec` similarity query execution
- **Reranker** — reciprocal rank fusion or weighted score merge across vector and FTS results. Pure math
- **Manifest manager** — read/write/update the manifest, track versions, compute staleness graphs
- **Summary differ** — detect if an article changed enough to warrant re-embedding versus a trivial edit (character-level diff ratio against a configurable threshold)

### Dual Summary Types

The Archivist maintains two summaries per article, each optimized for a different consumer:

- **Retrieval summary** — keyword-dense, optimized for search relevance. Used by the vector index and FTS for matching queries to articles. Emphasizes terminology, entity names, and distinctive vocabulary. **Generated by the Archivist deterministically** via keyword/entity extraction from the article text — no LLM inference required.
- **Content summary** — optimized for the Curator and Explorer's triage pass in the Multi-Pass Retrieval System. Captures the article's key claims, entities mentioned, relationships to other concepts, and conclusions. **Generated by the Compiler** as a deliverable of each compilation mission and handed to the Archivist for storage.

Both summaries are stored in `index/summaries.jsonl`:

```json
{
  "path": "wiki/concepts/regime-detection.md",
  "hash": "b7c1d4...",
  "embedding_version": 3,
  "retrieval_summary": "Regime detection HMM hidden Markov model BTC cryptocurrency volatility clustering COT commitment traders fear-greed index OOF accuracy...",
  "content_summary": "Covers three regime detection approaches tested across experiments 12, 23, and 31. Key finding: OOF accuracy as target variable outperforms direct regime labeling. Top predictive features are COT positioning and fear-greed index. HMM-based approach showed promise but suffered from lookback bias in walk-forward windows."
}
```

### Hybrid Retrieval

The Archivist runs two retrieval paths and merges results:

1. Vector similarity search over article summaries via `sqlite-vec`
2. Keyword search via SQLite FTS5

Results are merged and reranked by a lightweight scoring function. All results above a configurable relevance floor are returned — no arbitrary cap. This ensures exhaustive coverage while filtering noise.

```yaml
archivist:
  retrieval:
    vector_top_k: 50 # initial broad retrieval per index
    fts_top_k: 50 # initial broad retrieval per index
    relevance_floor: 0.3 # minimum merged score to return
    summary_type: content # which summary to include in results
```

### Indexing Trigger Modes

- `on_change` — event-driven, reindex immediately when the Compiler or Curator updates an article (stationed phase)
- `batch` — process all pending reindexing in one pass (CLI / build phase)

### Station Log Reporting

The Archivist is not an agent, but its health is reported in station logs like any system component: index size, retrieval latency, cache hit rates, summary freshness, embedding staleness. The Captain reads these metrics via the status aggregator toolkit.

---

## Multi-Pass Retrieval System

A shared retrieval pattern used by both the Curator (for article linking) and the Explorer (for query synthesis). The core principle: finding relevant articles should be exhaustive and cheap; reading them should be selective and targeted. Exhaustiveness and cost control are not in conflict when you separate finding from reading.

### Pass 1: Broad Scan (zero inference)

The requesting agent calls the Archivist system's retrieval interface — no LLM involved. The system runs vector similarity and FTS keyword match across the full index, plus backlink graph adjacency for the Curator's linking use case. All results above the relevance floor are returned with scores, content summaries, and file paths. No cap on result count.

At this stage, for a 200-article knowledge base, you might get 60 candidates. This costs nothing — it's database queries.

### Pass 2: Triage on Summaries (cheap inference)

The requesting agent's LLM reads the content summaries (not full articles) of all candidates. Content summaries are short — typically 100-200 words each. Even 60 summaries is only 6,000-12,000 words, well within a single context window.

The LLM classifies each candidate into three buckets:

- **Strong match** — clearly relevant, requires full article reading. For the Curator: needs bidirectional backlinks and content cross-referencing. For the Explorer: core source for synthesizing the answer.
- **Weak match** — tangentially related. For the Curator: deserves a "See also" reference. For the Explorer: worth mentioning but not worth deep reading.
- **No match** — irrelevant despite the retrieval signal. Skipped.

This pass is cheap because it reasons over summaries, not full articles. And it is exhaustive — every candidate is classified.

### Pass 3: Deep Read (targeted inference)

The requesting agent loads the full text of only the strong-match articles. If pass 2 identified 8 strong matches, only those 8 articles are loaded.

To manage context budget, articles are processed in configurable batches (default: 4 per inference call). The context budget calculator tool verifies that each batch fits within the model's context window.

For the **Curator**, this pass determines: what specifically should be cross-referenced, where backlinks should go in both the new and existing articles, and whether content in existing articles should be updated to reflect new connections.

For the **Explorer**, this pass synthesizes the answer with full contextual understanding and produces citations to specific articles and sections.

### Pass 4: Weak Match Resolution (minimal inference)

For weak matches, the full article is not read. The requesting agent uses only the information from the content summary (already available from pass 2).

For the **Curator**, this means adding a "Related" or "See also" reference — nearly a template operation that the backlink scanner tool can execute with minimal LLM involvement.

For the **Explorer**, weak matches may be mentioned briefly in the answer ("see also: [article]") without full synthesis.

### Summary Quality as Infrastructure

The multi-pass system's effectiveness depends entirely on content summary quality. A bad summary causes the LLM to misclassify a strong match as no-match, missing a critical connection. This elevates the Compiler's summary generation from a nice-to-have to core infrastructure — the Compiler produces the content summaries that the Curator and Explorer depend on for triage decisions. The Inspector should include summary quality checks in its sweep — flagging articles whose content summaries are stale, vague, or missing key claims.

**Quality gap during early phases:** The Inspector (which validates summary quality) is one of the last components built. All phases before it operate on Compiler-generated summaries with no automated quality gate. This is acceptable during development — output is reviewed manually — but the first Inspector sweep should anticipate a batch of summary-related findings that may require Compiler recompilation. Plan for this remediation pass when the Inspector comes online rather than treating it as a surprise.

### Short-Circuit for Small Knowledge Bases

During early expedition build or for small corpora, the multi-pass system is unnecessary overhead. If the total article count (or total word count) falls below a configurable threshold, the system skips passes 1-2 and loads all articles directly into context. This also means early compilation missions can proceed before the Archivist's index is fully built.

```yaml
multi_pass_retrieval:
  short_circuit_article_count: 15 # below this, load all articles directly
  short_circuit_word_count: 50000 # alternative trigger
  relevance_floor: 0.3 # minimum score from Archivist to enter pass 2
  deep_read_batch_size: 4 # articles per inference call in pass 3
  weak_match_style: see_also # how to handle tangential matches
  summary_quality_threshold: 0.5 # Inspector flags summaries below this quality
```

### Implementation Note

This is a shared module in `assistonauts-core/rag/multi_pass.py`, called by both the Curator and Explorer agents. The pass 1 retrieval and pass 4 weak-match resolution are identical. Passes 2 and 3 differ only in what the LLM does with the results (linking decisions vs. query synthesis), controlled by the calling agent's prompts.

---

## Agent Toolkits — Design Principles

Each agent has a `toolkit` attribute — a set of deterministic, zero-inference utilities that run either proactively (in the background, on schedule) or reactively (on-demand when the agent calls them). The agent calls the tool, gets structured results, and only then applies LLM reasoning to the output.

The mission execution pattern becomes: **tool scan → LLM reasoning on scan results → tool execution of LLM decisions → done.** The LLM is sandwiched between deterministic operations, never doing work a script could handle.

### Shared Toolkit (available to all agents)

- **Logger** — structured logging to mission log files
- **Config reader** — parse YAML configs, expedition definitions, agent configs
- **Cache interface** — check/read/write all three cache layers (content hash, LLM response, embedding)
- **File I/O** — read/write within owned directories, with ownership boundary enforcement
- **Archivist interface** — query the Archivist system for retrieval, indexing, and manifest operations

### Base Agent Class

```python
class Agent:
    role: str
    system_prompt: str
    toolkit: Toolkit          # deterministic utilities
    llm_client: LLMClient    # inference calls via litellm
    cache: CacheInterface     # shared cache layers
    archivist: Archivist     # knowledge base operating system
    owned_dirs: list[Path]    # directories this agent can write to
    readable_dirs: list[Path] # directories this agent can read from
```

The Archivist is not an agent subclass — it is a system dependency injected into every agent. See the Archivist section for its interface.

---

## Testing Strategy

The deterministic toolkits are straightforward to test with standard unit tests — given inputs, assert outputs. The LLM-driven agent behavior requires a different approach, since agent output is non-deterministic and quality is subjective.

### Three Testing Layers

**1. Contract tests (primary, run on every commit):**

Assert on the _structure_ of agent output without asserting on content quality. These use recorded LLM fixtures (see below) and verify that the agent's output conforms to expected formats:

- Compiler output has valid frontmatter, required sections per schema template, content summary present and under N words, source citations included
- Curator output contains valid wiki-internal links, backlink sections formatted correctly, no links to nonexistent articles
- Explorer output has citations to real articles, answer structured per output format
- Scout output is valid markdown, assets downloaded and referenced correctly
- Inspector findings have required severity levels, valid article references, actionable recommendations

Contract tests are fast, deterministic, and catch regressions in prompt engineering — if a prompt change breaks the output structure, the contract test fails immediately.

**2. Recorded fixtures (deterministic replay for development):**

Capture real LLM responses for a representative set of inputs and replay them in tests. The LLM client wrapper supports a `replay` mode that returns cached responses instead of making API calls:

```python
# Record mode: make real API calls, save request/response pairs
llm_client = LLMClient(mode="record", fixture_dir="tests/fixtures/")

# Replay mode: return saved responses, no API calls
llm_client = LLMClient(mode="replay", fixture_dir="tests/fixtures/")
```

Fixtures are committed to the repo. When agent prompts change significantly, fixtures are re-recorded. Stale fixtures are detected by a hash of the system prompt — if the prompt changes, the test warns that fixtures may need re-recording.

Recorded fixtures serve double duty: they make contract tests fast and deterministic, and they provide regression baselines for refactoring agent internals without changing behavior.

**3. Integration tests (slow, real LLM calls, run manually or in CI on a schedule):**

A small fixture corpus (5-10 source documents across different formats) with known expected outcomes. These tests make actual LLM calls and verify end-to-end behavior:

- Scout ingests a PDF and produces valid markdown
- Compiler produces an article from known sources that covers expected topics
- Curator links a new article to the correct existing articles
- Explorer answers a known question with citations to the right articles

Integration tests are expensive (tokens, latency) and non-deterministic, so they run separately from the unit/contract suite — either manually during development or on a scheduled CI job, not on every commit.

### Testing the Base Agent Class

The base agent class (Phase 1a) must be designed with testability in mind from the start:

- The LLM client is injected, not constructed — tests swap in a replay client
- Toolkit methods are independently testable (deterministic, no LLM)
- The agent's `run_mission()` method is the integration point: toolkit calls + LLM calls + output. Contract tests target this method with replay fixtures

This testing strategy shapes the base agent class design, which is why it is specified here rather than deferred to implementation.

---

## Agent Scaling

When workload exceeds a single agent instance's throughput — a large ingestion batch, a cascade of Compiler missions from a structural proposal, or concurrent Explorer queries — the system can scale parallelizable agents horizontally.

**Scaling rules by agent:**

| Agent     | Scalable       | Rationale                                                                                                                                             |
| --------- | -------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------- |
| Captain   | No (singleton) | Single coordination point, must maintain consistent state                                                                                             |
| Scout     | Yes            | Stateless file processing, naturally parallelizable                                                                                                   |
| Compiler  | Yes            | Independent article compilation, each mission targets a unique article                                                                                |
| Curator   | No (singleton) | Must maintain consistent view of the knowledge graph. Serializes all cross-referencing, which eliminates concurrent-backlink-write conflicts entirely |
| Inspector | No (singleton) | Sweep integrity — concurrent inspectors would produce conflicting or duplicate findings                                                               |
| Explorer  | Yes            | Independent query synthesis, no write conflicts                                                                                                       |

Note: the Archivist is a system component, not an agent. It is always available as a singleton service and does not participate in scaling decisions.

**Scaling configuration:**

Scaling and budget are deterministic systems. The Captain helps the user configure the rules during expedition setup (planning mode). At runtime, the scaling and budget systems operate based on those rules without requiring LLM judgment — queue depth thresholds, token budgets, max instances. The Captain receives system notifications for inclusion in station logs but does not make on-the-fly scaling or budget decisions.

```yaml
scaling:
  agents:
    scout: auto
    compiler: auto
    explorer: auto
  auto_scale:
    trigger: queue_depth > 5 # spin up when backlog builds
    max_instances: 3 # per agent type
    cooldown_minutes: 10 # before scaling back down
  budget:
    daily_token_limit: 100000 # mirrors expedition.stationed.resources.daily_token_budget
    warning_threshold: 0.8 # notify Captain at 80% spend
```

**Why the Curator singleton eliminates write conflicts:**

In the previous architecture, scaled Compilers created backlink collisions because multiple instances could try to update the same article's links simultaneously. With the Curator owning all cross-referencing as a singleton, this problem disappears by design. Compilers run in parallel producing articles and summaries — their only write target is their own primary article. All linking work funnels through the Curator sequentially after compilation completes. No staging, no reconciliation, no locks.

**SQLite concurrency ceiling:**

All three cache layers (content hash, LLM response, embedding) and the mission ledger use SQLite. With multiple scaled agents running in parallel, concurrent writes are serialized by SQLite's write lock — even in WAL mode, only one writer proceeds at a time.

For the v1 CLI with `max_instances: 3` per agent type, this is acceptable. The bottleneck in practice is LLM API latency (seconds per call), not database write throughput (microseconds per write). Agents spend >99% of their time waiting on inference, so write contention is negligible.

However, this is a known scaling ceiling. If future workloads require higher write throughput (e.g., 10+ concurrent agents, or a server deployment handling multiple expeditions), the SQLite backends should be replaced. The spec already plans Postgres for the server deployment (`assistonauts-server`), which resolves this. For the CLI, the ceiling should be documented in the scaling configuration so it is not discovered by surprise when the scaling system is implemented.

---

## Data Architecture

```
workspace/
├── raw/                        # Scout owns
│   ├── papers/
│   ├── articles/
│   ├── repos/
│   ├── datasets/
│   └── assets/                 # images, diagrams downloaded locally
│
├── wiki/                       # Compiler owns
│   ├── _schema.md              # wiki conventions, templates, taxonomy
│   ├── _index.md               # master index (Archivist maintains)
│   ├── concepts/               # concept articles
│   ├── entities/               # people, tools, datasets, methods
│   ├── logs/                   # experiment logs, field notes
│   └── explorations/           # Explorer files answers here
│
├── index/                      # Archivist system owns
│   ├── assistonauts.db         # sqlite-vec + FTS5 combined database
│   ├── summaries.jsonl         # dual summaries (retrieval + content) per article
│   └── manifest.json           # content hashes, processing timestamps, lineage
│
├── audits/                     # Inspector owns
│   ├── sweep-2026-04-05.md     # audit report
│   └── findings/               # individual findings pending review
│
├── expeditions/                # expedition definitions and state
│   └── autotrader-research/
│       ├── expedition.yaml     # expedition config
│       ├── plan.yaml           # Captain's mission plan
│       ├── review/             # pending review items (YAML)
│       └── missions/           # mission definitions, logs, and status
│           ├── mission-0001.yaml
│           └── mission-0001.log.md
│
├── station-logs/               # Captain's reports
│   └── 2026-W14.md
│
└── .assistonauts/              # system config
    ├── config.yaml             # global config
    ├── agents/                 # agent role definitions
    │   ├── captain.yaml
    │   ├── scout.yaml
    │   ├── compiler.yaml
    │   ├── curator.yaml
    │   ├── inspector.yaml
    │   └── explorer.yaml
    ├── cache/
    │   └── llm_cache.db        # LLM response cache
    ├── ledger.db               # mission state ledger (SQLite, source of truth)
    └── hooks/                  # pre/post mission hooks
```

### Workspace Versioning

The workspace is git-tracked from initialization. The markdown-everywhere architecture makes this trivial and provides the audit trail the system values:

- `assistonauts init` runs `git init` as part of workspace creation
- The mission runner commits after each completed mission, with the mission ID and agent in the commit message: `[mission-0042] compiler: compile spectral-analysis article`
- Curator backlink updates are committed separately from Compiler content edits, preserving the distinction in the audit trail
- Inspector sweep reports are committed as a batch after the sweep completes
- `.assistonauts/cache/` and `index/assistonauts.db` are gitignored (derived data, large binaries). The manifest (`index/manifest.json`) and summaries (`index/summaries.jsonl`) are tracked since they contain human-meaningful metadata

This approach avoids the noise concern of per-file-write commits by committing at mission boundaries — a natural unit of work with a meaningful description. The git history becomes a readable log of what each agent did and why, complementing the YAML mission audit trail. Rollback is straightforward: `git revert` a bad mission commit to undo a Compiler rewrite or Curator linking pass.

### File Ownership Boundaries

| Entity             | Owns                                                           | Can read                                  |
| ------------------ | -------------------------------------------------------------- | ----------------------------------------- |
| Captain            | `expeditions/`, `station-logs/`                                | Everything                                |
| Scout              | `raw/`                                                         | `expeditions/` (scope definition)         |
| Compiler           | `wiki/` (article content, except `_index.md`, `explorations/`) | `raw/`, `expeditions/` (scope definition) |
| Curator            | Backlink sections within `wiki/` articles                      | `wiki/`, `index/` (via Archivist system)  |
| Inspector          | `audits/`                                                      | `raw/`, `wiki/`, `index/manifest.json`    |
| Explorer           | `wiki/explorations/`                                           | `wiki/`, `index/` (via Archivist system)  |
|                    |                                                                |                                           |
| Archivist (system) | `index/`, `wiki/_index.md`                                     | `wiki/`                                   |

### Wiki Schema (`_schema.md`)

The `_schema.md` file is the constitution of the knowledge base. It defines article templates, frontmatter format, categorization taxonomy, naming conventions, and structural rules that the Compiler and Curator follow when writing and linking articles.

**Creation:** Generated during expedition initialization. The Captain produces a default schema based on the expedition's scope and domain, or the human provides a custom schema. The schema is a markdown file — human-readable, version-controllable, and editable.

**Contents:**

- Article templates per type (concept page, entity page, experiment log, exploration)
- Required frontmatter fields (title, sources, compiled date, tags)
- Categorization taxonomy (top-level categories, subcategory rules)
- Naming conventions (file naming, link formatting)
- Backlink formatting rules (where "Related" and "See also" sections go)
- Any domain-specific structural conventions

**Governance:** The Curator may propose changes to the schema (new categories, structural reorganization) via the review queue. Schema changes require human approval — they affect the entire knowledge base's structure. The Captain applies approved schema changes directly (the schema is an expedition-level governance document, not a wiki article — the Compiler should not edit the document that governs its own behavior). Approved changes may trigger retroactive missions to bring existing articles into compliance.

**Consumers:** The Compiler uses the schema for article templates and frontmatter. The Curator uses it for linking conventions and categorization. The Inspector uses it for schema validation checks (flagging articles that don't conform).

---

## Technology Stack

### Core Engine (`assistonauts-core`)

The shared engine across all deployment surfaces.

```
assistonauts-core/
├── agents/               # agent role implementations
│   ├── base.py           # base agent class with toolkit integration
│   ├── captain.py
│   ├── scout.py
│   ├── compiler.py
│   ├── curator.py
│   ├── inspector.py
│   └── explorer.py
├── archivist/            # knowledge base operating system (not an agent)
│   ├── system.py         # main Archivist class with service interface
│   ├── embeddings.py     # embedding generation and storage
│   ├── fts.py            # FTS5 indexing
│   ├── retrieval.py      # hybrid search (vector + FTS + rerank)
│   ├── manifest.py       # manifest management, staleness tracking
│   └── summaries.py      # dual summary storage and keyword extraction
├── tools/                # deterministic agent toolkits
│   ├── shared.py         # logger, config reader, cache interface, file I/O
│   ├── captain.py        # queue manager, budget tracker, schedule runner, status aggregator
│   ├── scout.py          # format converters, web clipper, file watcher, hasher, dedup checker
│   ├── compiler.py       # diff generator, template engine, article stats
│   ├── curator.py        # backlink scanner, graph analyzer
│   ├── inspector.py      # link checker, orphan detector, staleness scanner, duplicate detector, schema validator, freshness checker
│   └── explorer.py       # citation formatter, context budget calculator, output renderer
├── missions/             # mission runner, state machine
│   ├── runner.py
│   ├── states.py
│   └── planner.py        # Captain's planning logic
├── expeditions/          # expedition orchestrator
│   ├── orchestrator.py
│   └── triggers.py       # event/schedule trigger system
├── rag/                  # multi-pass retrieval (uses Archivist for underlying search)
│   └── multi_pass.py     # shared multi-pass retrieval system for Curator and Explorer
├── cache/                # caching layers
│   ├── content.py        # content hash cache (manifest)
│   ├── llm.py            # LLM response cache
│   └── embedding.py      # embedding version tracking
├── storage/              # file system abstraction
│   └── workspace.py      # workspace directory management, file I/O with ownership enforcement
├── llm/                  # LLM provider abstraction
│   └── client.py         # wraps litellm
└── config/               # configuration loading
    └── loader.py
```

### Deployment Wrappers

```
assistonauts-cli/         # CLI wrapper (click + rich)
assistonauts-server/      # API server (FastAPI) for SaaS/self-hosted
assistonauts-web/         # web UI (expedition dashboard, explorer REPL)
```

### Dependencies (Core)

| Package                | Purpose                                                            |
| ---------------------- | ------------------------------------------------------------------ |
| `litellm`              | Provider-agnostic LLM calls (Claude, OpenAI, Ollama, Vertex, etc.) |
| `sqlite-vec`           | Vector similarity search                                           |
| `pyyaml`               | Configuration                                                      |
| `click`                | CLI framework                                                      |
| `rich`                 | Terminal UI, progress indicators, tables                           |
| `watchdog`             | File system watching for Scout stationed mode                      |
| `markitdown`           | PDF/HTML/DOCX to markdown conversion for Scout                     |
| `feedparser`           | RSS feed parsing for Scout source watching                         |
| Standard lib `sqlite3` | Cache storage, mission state, FTS5                                 |
| Standard lib `hashlib` | Content hashing                                                    |

No LangChain. No LlamaIndex. No heavyweight frameworks. The orchestration and toolkits are simple enough to own entirely.

### Dependencies (Server — deferred)

| Package           | Purpose                               |
| ----------------- | ------------------------------------- |
| `fastapi`         | API layer                             |
| `celery` or `arq` | Async mission execution               |
| `postgres`        | Multi-tenant state (replaces SQLite)  |
| `redis`           | LLM response cache, job queue backend |

### LLM Configuration

Provider-agnostic with role-to-provider mapping:

```yaml
llm:
  providers:
    anthropic:
      model: claude-sonnet-4-20250514
      api_key_env: ANTHROPIC_API_KEY
    ollama:
      model: llama3.2
      base_url: http://localhost:11434

  roles:
    captain: anthropic # strategic planning and judgment — few calls, high stakes
    scout: ollama # high volume, simple processing
    compiler: anthropic # needs strong reasoning and synthesis
    curator: anthropic # broad understanding of concept landscape for linking
    inspector: anthropic # needs careful analytical judgment
    explorer: anthropic # synthesis quality matters
```

### Embedding Configuration

```yaml
embedding:
  providers:
    ollama:
      model: nomic-embed-text
      base_url: http://localhost:11434
    vertex:
      model: text-embedding-005
      project: my-gcp-project

  active: ollama # or vertex for cloud deployments
```

### Vision Capabilities

For expeditions with image-heavy sources (research papers with figures, trail photos, maps, diagrams), the Scout and Compiler need vision-capable models to fully process the content.

**Scout:** When ingesting sources that contain images, a vision-capable model can extract information from diagrams, charts, and photographs during the markdown conversion step. Without vision, the Scout preserves images as local assets but cannot describe or interpret them — downstream agents only see `![image](path)` references.

**Compiler:** When compiling articles from sources that include essential images (a paper whose key contribution is a figure, field notes with trail photos), a vision-capable model can incorporate visual information into the article's narrative and summary. Without vision, the Compiler works from text only and may miss critical information encoded visually.

```yaml
vision:
  enabled: true
  providers:
    anthropic:
      model: claude-sonnet-4-20250514 # supports vision
      supports_vision: true
    ollama:
      model: llama3.2
      supports_vision: false

  # Roles that need vision — must map to a vision-capable provider
  vision_roles: [scout, compiler]

  # Fallback behavior when a role needs vision but its provider doesn't support it
  fallback: extract_text_only # or: skip_images | escalate_to_vision_provider
```

When `fallback` is set to `escalate_to_vision_provider`, the Scout or Compiler temporarily uses a vision-capable provider for image-containing sources while using the cheaper provider for text-only sources. This keeps costs down while handling image-heavy expeditions correctly.

---

## Caching Architecture

Three caching layers, each solving a distinct problem. Caching is a first-class system concern, not an optimization to add later.

### 1. Content Hash Cache

**Purpose:** Avoid reprocessing unchanged sources.

Every file in `raw/` and `wiki/` is tracked by SHA-256 content hash in the manifest. Before any agent processes a file, it checks the hash. If unchanged, the operation is skipped.

**Stored in:** `index/manifest.json`

```json
{
  "raw/papers/fft-analysis.md": {
    "hash": "a3f2e8...",
    "last_processed": "2026-04-05T12:00:00Z",
    "processed_by": "scout",
    "downstream": ["wiki/concepts/spectral-analysis.md"]
  },
  "wiki/concepts/spectral-analysis.md": {
    "hash": "b7c1d4...",
    "last_compiled": "2026-04-05T12:05:00Z",
    "sources": ["raw/papers/fft-analysis.md", "raw/papers/spectral-entropy.md"],
    "embedding_version": 3,
    "last_indexed": "2026-04-05T12:06:00Z",
    "summary_version": 3,
    "last_summarized": "2026-04-05T12:05:00Z"
  }
}
```

**Invalidation:** Unidirectional. A change in `raw/` invalidates dependent `wiki/` articles, which invalidates both their embeddings and their content summaries. The full invalidation chain:

```
raw/ source changes → compiled article stale → content summary stale → embedding stale
```

The manifest tracks the full lineage. The Archivist checks `summary_version` against the article's content hash to know when to expect an updated content summary from the Compiler. Until the Compiler delivers the updated summary, the Archivist retains the previous version (stale data is better than no data for retrieval purposes).

### 2. LLM Response Cache

**Purpose:** Avoid identical inference calls across development iterations and repeated queries.

Hashes the full prompt (system prompt + messages + model identifier) and caches the response. Critical during development when iterating on agent prompts against the same sources.

**Stored in:** `.assistonauts/cache/llm_cache.db` (SQLite)

```yaml
cache:
  llm_responses:
    enabled: true
    backend: sqlite # sqlite for CLI, redis for server
    ttl_hours: 168 # one week default
    max_size_mb: 500
    key_strategy: prompt_hash # SHA-256 of full prompt
```

**Cache key:** `SHA-256(model + system_prompt + messages)`

**Invalidation:** TTL-based. Can also be manually flushed per agent role or per expedition.

### 3. Embedding Cache

**Purpose:** Avoid recomputing vectors for unchanged articles.

Each article in the manifest tracks an `embedding_version` integer. When the Compiler updates an article, the content hash changes and the embedding is marked stale. The Archivist only recomputes embeddings where the article's content hash is newer than the indexed version.

**Stored in:** `index/manifest.json` (version tracking) and `index/assistonauts.db` (actual vectors)

**Invalidation:** Triggered by content hash change in the manifest.

### Cache Interaction by Agent / System

| Entity             | Content Cache                   | LLM Cache                        | Embedding Cache              |
| ------------------ | ------------------------------- | -------------------------------- | ---------------------------- |
| Captain            | Reads manifest for status       | Reads/writes (planning prompts)  | —                            |
| Scout              | Writes hashes on ingest         | Reads/writes (format conversion) | —                            |
| Compiler           | Checks before recompiling       | Reads/writes (primary consumer)  | —                            |
| Curator            | —                               | Reads/writes (linking decisions) | —                            |
| Inspector          | Reads for change detection      | Reads/writes (analysis prompts)  | —                            |
| Explorer           | —                               | Reads/writes (query responses)   | —                            |
|                    |                                 |                                  |                              |
| Archivist (system) | Reads/writes staleness tracking | —                                | Reads/writes (primary owner) |

---

## Expedition Lifecycle

### Build Phase

The build phase follows an iterative planning model — analogous to a real expedition where you cannot fully plan for an environment you haven't yet discovered. The Captain plans, executes a batch, observes what was learned, and replans.

```
1. Human creates expedition.yaml with scope, sources, and agent config
2. Human: "Captain, start the expedition"
3. Captain reads expedition config

ITERATION 1 — Discovery:
4. Captain produces a preliminary plan based on source metadata
   (file names, paths, types — not content, which hasn't been read yet):
   a. Scout missions to ingest all configured sources
   b. Initial Compiler missions for the first batch of ingested sources
   c. Archivist system builds initial index after first compilation batch
5. Scout ingests sources, Compiler compiles first batch of articles
6. Archivist system automatically indexes each article and stores summaries
7. Captain observes: what concepts emerged? What dependencies exist?

ITERATION 2 — Structuring:
8. Captain revises the plan based on compiled content:
   a. Identifies foundational concepts that other articles will reference
   b. Sequences remaining Compiler missions with correct dependencies
   c. Identifies structural needs (categories, entity pages)
9. Compiler processes remaining sources in dependency order
10. Archivist system indexes new articles automatically
11. Captain observes: is the concept landscape complete?

ITERATION 3 — Refinement:
12. Captain assigns retroactive cross-referencing pass:
    a. Curator runs multi-pass linking across all articles
       (early articles compiled without full index now get proper backlinks)
    b. Archivist system reindexes updated articles

Note: the Curator intentionally waits until iteration 3 rather than
cross-referencing incrementally during iterations 1-2. Running the
Curator after every Compiler mission during build would mean repeated
multi-pass retrieval against an incomplete corpus — wasteful, since
many links would change as more articles arrive. Better to compile
the full concept landscape first, then cross-reference once
comprehensively.
13. Inspector runs full sweep
14. Captain reviews Inspector findings, routes to review queue

COMPLETION:
15. Captain produces a build report summarizing the knowledge base
16. Human reviews the knowledge base, resolves pending review items
17. Human: "Captain, station the agents"
18. Captain transitions expedition to stationed phase
```

The number of iterations may vary by expedition. A small, well-scoped expedition might complete in two iterations. A large expedition with complex interdependencies might require four or five. The Captain determines when iteration is complete based on: all sources processed, all linking passes done, Inspector sweep clean or findings addressed.

### Stationed Phase

```
Ongoing loop:
1. Scout watches configured sources
2. On new source detected:
   a. Scout ingests and reports to Captain
   b. Captain creates Compiler mission for the new source
   c. Compiler compiles article and generates content summary
   d. Archivist system automatically indexes article and stores summaries
   e. Curator cross-references the new article against existing wiki
   f. Inspector validates consistency with existing knowledge
3. On scheduled Inspector sweep:
   a. Inspector runs deterministic tools first (link check, staleness scan, etc.)
   b. Inspector LLM analyzes flagged items for semantic issues
   c. Findings reported to Captain
   d. Captain triages: auto-fix low-risk, queue high-risk for human review
   e. Compiler missions created for approved fixes
4. On Explorer query (interactive or mission):
   a. Explorer uses multi-pass retrieval (via Archivist system) to find relevant articles
   b. Explorer synthesizes answer
   c. If answer is high-value, filed to wiki/explorations/
   d. Archivist system indexes the exploration (available for queries, not yet wiki-integrated)
   e. Exploration enters review queue for human approval before wiki integration
5. Captain produces station logs on configured schedule
```

### Cycle Guard

The Inspector must not re-audit articles that were just fixed based on its own findings in the same sweep. Each Inspector sweep is tagged with an ID. Compiler fixes reference the finding ID they resolve. The Inspector skips articles whose only changes since the last sweep are finding-resolution commits.

Additionally, Curator backlink additions (updating "Related" and "See also" sections) do not trigger re-audit. These are structural cross-referencing changes, not content changes — they don't affect the article's claims or accuracy. The Inspector distinguishes between content modifications (Compiler edits, which may warrant re-audit) and link-section modifications (Curator edits, which do not).

---

## Human Review Workflow

The Captain manages a review queue for decisions that require human approval. The human is the ultimate authority — no content enters the wiki proper without human sign-off on the pathway that put it there.

**Items that enter the review queue:**

- Inspector findings at `warning` or `critical` severity (configurable)
- Curator proposals for new categories or structural reorganization
- Scout source rejections at borderline relevance scores
- Explorer explorations pending promotion to the wiki (requires both human approval and Captain sign-off before entering the incorporation workflow)
- Any mission that fails after max retries

**Review item structure:**

All review items share a common YAML structure with a `type` field for filtering:

```yaml
review_item:
  id: review-0017
  type: inspector_finding # inspector_finding | curator_proposal | scout_borderline | exploration_promotion | mission_failure
  severity: critical # critical | warning | info
  created_at: 2026-04-09T14:30:00Z
  created_by: inspector
  summary: "Contradiction between spectral-analysis.md and experiment-37-results.md"
  details:
    articles:
      [wiki/concepts/spectral-analysis.md, wiki/logs/experiment-37-results.md]
    recommendation: "Update spectral-analysis.md to reflect experiment 37 findings"
  status: pending # pending | approved | dismissed | deferred
  resolved_at: null
  resolved_by: null
```

**Review interface (CLI v1):**

```
$ assistonauts review

Expedition: autotrader-research
Pending review items: 4

[1] CRITICAL (inspector_finding) — Contradiction detected
    spectral-analysis.md says FFT features ranked #1
    experiment-37-results.md shows COT features outperformed FFT
    Inspector recommends: update spectral-analysis.md
    → approve | dismiss | inspect

[2] WARNING (curator_proposal) — New category proposed
    Curator suggests creating concepts/capital-efficiency/
    Based on: 4 articles reference capital efficiency with no dedicated page
    → approve | dismiss | defer

[3] INFO (scout_borderline) — Source relevance borderline
    Scout filtered: "Attention Mechanisms in Time Series" (score: 0.58)
    Expedition threshold: 0.60
    → ingest | dismiss

[4] INFO (exploration_promotion) — Exploration ready for review
    wiki/explorations/regime-detection-comparison.md
    Explorer synthesis of 4 articles on regime detection approaches
    → approve | dismiss | inspect
```

**Actions:**

- `approve` — item is accepted. Inspector findings generate Compiler fix missions. Curator proposals generate new missions. Explorations enter the standard ingestion flow (Compiler compiles, Curator links). Scout borderlines get ingested.
- `dismiss` — item is rejected with optional reason. Archived for audit trail.
- `defer` — item stays in queue, deprioritized. Revisited in next station log.
- `inspect` — prints the relevant article sections or exploration content to the terminal for human reading. A simple print function in v1, subject to improvement (e.g., diff view, side-by-side comparison).
- `ingest` — Scout-specific: override the relevance filter and ingest the source.

**Review storage:** `expeditions/<n>/review/` — pending items as YAML files with the structure above. Approved/dismissed items archived with the human’s decision, timestamp, and optional reason for audit trail.

**Review queue summarization:**

When review items accumulate, the Captain groups and summarizes them for presentation rather than showing a flat list. This prevents the human from being overwhelmed after a large build phase or a period away:

```
$ assistonauts review

Expedition: autotrader-research
Pending review items: 14

Auto-resolved (per policy): 8 broken link fixes applied
Needs your input:
  Contradictions (critical): 2 items
  Structural proposals: 3 items
  Exploration promotions: 1 item

Enter a category to review, or 'all' for the full list.
```

The human drills into the categories they care about. Auto-resolved items are reported for awareness but don’t require action.

**Work stalling without human approval:**

When review items require human approval, dependent work stalls until the human acts. The system does not route around unresolved reviews — this is intentional. Approved explorations don’t enter the wiki until the human says so. Structural proposals don’t generate new missions until approved. Critical contradictions block further compilation of affected articles.

The system continues operating on unrelated work (new source ingestion, compilation of unaffected articles, Explorer queries) but will not proceed on review-dependent paths. This ensures the human remains the ultimate authority over knowledge base integrity.

Autonomous mode — where the station runs without human intervention using configurable approval policies — is a future feature, not part of v1.

**Stale review escalation:**

The Captain tracks how long review items have been pending. Items older than a configurable threshold (default: 7 days) are escalated in the station log:

```
### Stale Review Items
- [14 days pending] CRITICAL: Contradiction between spectral-analysis.md and experiment-37-results.md
- [9 days pending] WARNING: Structural proposal for concepts/capital-efficiency/
```

This ensures pending items don’t silently rot. The Captain surfaces them weekly until resolved.

---

## Station Log Format

Weekly report produced by the Captain:

```markdown
# Station Log — autotrader-research

## Week of April 5, 2026

### Summary

- New sources ingested: 3
- Articles updated: 7
- Articles created: 2
- Cross-references created: 15 (Curator)
- Backlinks added to existing articles: 23 (Curator)
- Inspector findings: 4 (3 auto-fixed, 1 pending review)
- Explorer queries answered: 12 (2 filed to explorations)
- Stale articles remaining: 0
- Cache hit rate: 73%

### Token Usage

- Total tokens: 47,200
- By agent: Captain 2,100 | Scout 4,300 | Compiler 22,400 | Curator 7,200 | Inspector 8,900 | Explorer 2,300

### New Sources

- raw/papers/regime-switching-hmm.pdf (Scout, April 6)
- raw/articles/fear-greed-methodology.md (Scout, April 7)
- raw/experiments/experiment-38.md (Scout watch, April 9)

### Notable Changes

- concepts/regime-detection.md — major update incorporating HMM approach
- entities/fear-greed-index.md — methodology section added
- explorations/feature-importance-timeline.md — new exploration filed

### Pending Review

- [1 item] Contradiction: spectral-analysis.md vs experiment-37-results.md

### Knowledge Base Health

- Total articles: 49 (was 45 last week)
- Total words: 201,000
- Coverage: 12 concept areas (+1), 23 entities (+3)
- Orphaned articles (no inbound links): 1
- Average backlinks per article: 4.2
- Articles with stale summaries: 0
- Inspector issues resolved this week: 3
- Unresolved contradictions: 1
- Exploration promotion rate: 1 of 2 filed (50%)
- Cross-referencing density: 82% of articles linked to 2+ others
```

Knowledge base health metrics are designed to resist gaming — raw growth numbers (article count, word count) are reported alongside qualitative indicators (orphan rate, cross-referencing density, contradiction count, summary freshness) that reflect actual knowledge base integrity and interconnectedness.

---

## CLI Interface

### Core Commands

```bash
# Initialize a new workspace
assistonauts init

# Create a new expedition
assistonauts expedition create --config expedition.yaml

# Start the build phase
assistonauts build <expedition-name>

# Run a single mission manually
assistonauts mission run --agent compiler --type compile_article --input raw/papers/fft.md

# Station agents after build review
assistonauts station <expedition-name>

# Pause all agent activity (vacation, budget limit, manual review)
assistonauts pause <expedition-name>

# Resume a paused expedition
assistonauts resume <expedition-name>

# Interactive explorer session
assistonauts explore <expedition-name>

# Review pending items
assistonauts review [<expedition-name>]

# View station log
assistonauts log [<expedition-name>] [--week 2026-W14]

# View expedition status
assistonauts status [<expedition-name>]

# Cache management
assistonauts cache stats
assistonauts cache flush [--agent compiler] [--expedition autotrader-research]

# Agent-specific commands
assistonauts scout ingest <path-or-url>
assistonauts inspector sweep [<expedition-name>]
```

### Interactive Explorer REPL

```
$ assistonauts explore autotrader-research

Captain: Knowledge base loaded. 49 articles, 201K words. Ready for queries.

You: What regime detection approaches have I tried and what were the failure modes?

Explorer: Searching knowledge base...
  → Loading: concepts/regime-detection.md
  → Loading: experiments/experiment-12.md
  → Loading: experiments/experiment-23.md
  → Loading: experiments/experiment-31.md
  → Loading: concepts/hidden-markov-models.md

[synthesized answer with citations to wiki articles]

Explorer: File this answer to explorations? [y/n]

You: y

Explorer: Filed to wiki/explorations/regime-detection-comparison.md
Captain: Archivist reindexing... done.
```

---

## Initial Expeditions

Two expeditions to validate the framework during dogfooding:

### Expedition 1: Autotrader Research

**Scope:** Machine learning approaches to BTC/USD price prediction — feature engineering, regime detection, walk-forward validation, scoring methodology, capital efficiency.

**Sources:**

- 37+ experiment logs and results
- FFT / spectral analysis research papers
- COT and fear-greed feature research
- Walk-forward validation literature
- Regime detection methodology papers
- Chat history extracts on architecture decisions

**Expected wiki structure:**

- Concepts: feature engineering, regime detection, walk-forward validation, scoring formulas, capital efficiency, signal dampening, position sizing
- Entities: HistGradientBoosting, COT report, fear-greed index, CME Micro Bitcoin futures
- Logs: experiment results with cross-references to which concepts/approaches each tested
- Explorations: synthesis articles on failure modes, feature importance evolution, architecture decisions

**Value demonstrated:** Technical ML research knowledge management. Shows how accumulated experimental knowledge compounds rather than getting lost in chat history and scattered files.

### Expedition 2: Lion's Share Treasure Hunt

**Scope:** Analytical research for the Collins-Black treasure hunt — poem analysis, field reconnaissance, geological and geographical data, community intelligence.

**Sources:**

- Poem texts and haiku analysis
- Field notes from Rocky Face Mountain expeditions
- Trail marker data and GPS coordinates
- Geological survey data for Alexander County
- Collins-Black's published clues and social media
- Community forum discussions and theories
- Interactive search map data

**Expected wiki structure:**

- Concepts: haiku encoding theory, triangulation geometry, marker interpretation
- Entities: Rocky Face Mountain, trail markers (305, 311, 317, 318), Alexander County, Collins-Black
- Logs: field expedition notes with photos and GPS data
- Explorations: hypothesis synthesis, connection analysis between clues

**Value demonstrated:** Creative/analytical research knowledge management. Very different domain from ML, same infrastructure — validates the framework's generality.

---

## Open Questions

1. **Cross-expedition queries.** Can an Explorer query across multiple knowledge bases? Deferred to post-v1, but the workspace isolation should not prevent it architecturally.

2. **Collaborative expeditions.** Multiple humans contributing sources to the same expedition. Relevant for team/enterprise use. Requires auth and conflict resolution. Deferred to server deployment.

3. **Export formats.** The knowledge base is markdown, but clients may want HTML, PDF, or hosted wiki output. A rendering layer could sit on top of the wiki without changing the core architecture.

4. **Agent customization.** Can users define custom agent roles beyond the six? A plugin system where the core six are built-in but additional specialists can be added per expedition. Deferred to post-v1.

5. **Exploration promotion criteria.** What determines whether an exploration gets approved for wiki integration? Currently purely human judgment via the review queue. Could the Inspector apply quality criteria (minimum source citations, consistency with existing articles, sufficient depth) to pre-screen explorations before they reach the human? This would reduce review burden as exploration volume grows. The risk is that automated criteria gate out novel insights that don't fit existing patterns — the exact kind of discovery explorations are meant to surface.

---

# Appendix: Development Roadmap

> **Important distinction:** This section describes the order in which the Assistonauts _software_ is built. It is not the order in which agents operate during an expedition. In production, all six agents and the Archivist system are available from expedition start. The phased development approach allows incremental validation of each component.

### Phase 1 — Core Infrastructure + Scout

Establish the foundation that every subsequent phase builds on. Getting the base agent class and toolkit integration pattern right here is critical — every agent inherits it.

Build `assistonauts-core` with:

- Workspace initialization and directory structure (including `git init` — see Workspace Versioning)
- Config loading (YAML)
- Base agent class with toolkit integration and injectable LLM client (designed for testability — see Testing Strategy)
- LLM client wrapper (litellm) with record/replay mode for test fixtures
- Shared toolkit (logger, config reader, cache interface, file I/O with ownership enforcement)
- Content hash cache (manifest)
- Scout agent with toolkit (format converters, content hasher, web clipper)
- Contract test infrastructure and initial recorded fixtures for Scout
- CLI: `init`, `scout ingest`

**Validation:** Initialize a workspace, drop a PDF into `raw/`, run Scout to convert it to markdown. Content hash prevents re-processing on second run. Contract tests verify Scout output structure. The base agent class supports LLM client injection for testing.

### Phase 2 — Compiler + Mission Runner

Build the compilation pipeline on top of the Phase 1 foundation.

- Wiki schema (`_schema.md`) definition and template engine
- Compiler agent with toolkit (diff generator, template engine, article stats)
- Minimal mission runner (single mission execution, with failure classification — see Mission section)
- Mission-level git commits (mission runner commits after each completed mission)
- Contract tests and recorded fixtures for Compiler
- CLI: `mission run --agent compiler`

**Validation:** Run Scout to ingest a source, then run Compiler via the mission runner to produce a wiki article with valid frontmatter and schema-conformant structure. Git log shows mission-level commits. Contract tests verify Compiler output structure. Note: articles compiled in this phase lack cross-referencing (Archivist system and Curator not yet available). This is expected — Phase 3 includes retroactive cross-referencing.

### Phase 3 — Archivist System + Curator + Hybrid RAG

- Archivist system (not an agent — deterministic knowledge base operating system)
  - Embedding generation, FTS indexing, vector search, reranking
  - Manifest management with full lineage and summary staleness tracking
  - Dual summary storage (retrieval summaries generated deterministically, content summaries received from Compiler)
  - Service interface callable by all agents
- `sqlite-vec` + FTS5 hybrid retrieval with relevance floor
- Multi-pass retrieval system (shared module for Curator and Explorer)
- Short-circuit mode for small knowledge bases
- Curator agent with toolkit (backlink scanner, graph analyzer)
- Embedding cache
- LLM response cache
- Retroactive cross-referencing pass for Phase 1-2 articles (Curator)
- CLI: `assistonauts status`

**Validation:** Compile 10+ articles, Archivist system indexes them with dual summaries, verify retrieval quality. Curator cross-references a new article and verify multi-pass linking discovers all relevant connections. Verify Phase 1-2 articles are retroactively linked.

### Phase 4 — Explorer + Interactive Mode

- Explorer agent with toolkit (citation formatter, context budget calculator, output renderer)
- Query flow via shared multi-pass retrieval system (through Archivist system)
- Interactive REPL for CLI
- Filing answers to `wiki/explorations/`
- CLI: `assistonauts explore`

**Validation:** Ask complex questions against the knowledge base and get synthesized answers with article citations. Verify multi-pass triage correctly identifies strong vs. weak matches.

### Phase 5 — Captain + Expedition Orchestration

- Captain agent with toolkit (mission queue manager, mission ledger, token budget tracker, schedule runner, status aggregator)
- Iterative planning (plan → execute batch → observe → replan)
- Expedition lifecycle (build phase orchestration)
- Mission state machine with acceptance criteria and checklists
- Mission dependency resolution
- Deterministic scaling system (concurrent Compiler/Scout/Explorer instances, Curator singleton serializes all cross-referencing). Note: SQLite write concurrency is a known ceiling at this stage — see Agent Scaling section
- Deterministic budget system (hard caps, thresholds, notifications)
- CLI: `assistonauts expedition create`, `assistonauts build`

**Validation:** Create an expedition config, Captain produces an iterative plan, executes it end-to-end with proper sequencing. Test scaling with concurrent Compiler instances on a large source batch.

### Phase 6 — Inspector + Quality + Review

- Inspector agent with toolkit (link checker, orphan detector, staleness scanner, duplicate detector, schema validator, source freshness checker)
- Deterministic-scan-first sweep pattern (tools run first, LLM analyzes flagged items only)
- Audit report generation
- Finding → Compiler mission pipeline
- Human review queue with typed review items and Captain grouping/summarization
- Exploration promotion pipeline (Inspector technical quality check → human approval → standard ingestion flow)
- Summary quality checks (Inspector validates Compiler-generated content summaries). Note: the first Inspector sweep should anticipate a batch of summary-quality findings from Phases 2-5 — plan for this remediation pass rather than treating it as a surprise
- CLI: `assistonauts inspector sweep`, `assistonauts review`

**Validation:** Introduce deliberate contradictions, broken links, and gaps. Verify deterministic tools catch mechanical issues. Verify LLM catches semantic contradictions. Compiler fixes approved findings. File an exploration and verify the full promotion pipeline (Inspector review → human approval → Compiler recompiles → Curator links).

### Phase 7 — Stationed Mode

- Watch system (directory watcher, RSS, GitHub, web scraping)
- Trigger/event system
- Scheduled execution (cron-based)
- Station log generation with knowledge base health metrics
- Stale review item escalation
- Cycle guards
- Pause/resume support
- CLI: `assistonauts station`, `assistonauts log`, `assistonauts pause`, `assistonauts resume`

**Validation:** Station agents on autotrader expedition, add new experiment results, observe the full pipeline fire automatically (Scout → Compiler → Archivist system → Curator → Inspector). Verify station log produces accurate health metrics. Test pause/resume.
