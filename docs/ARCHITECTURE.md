# Assistonauts — Technical Architecture

## System Overview

```
                          ┌─────────────────────────────────────────────┐
                          │              Human (CLI)                     │
                          │  init | scout ingest | mission run | explore │
                          │  review | build | station | status          │
                          └────────────────────┬────────────────────────┘
                                               │
                          ┌────────────────────▼────────────────────────┐
                          │              CLI Layer (Click + Rich)        │
                          │         assistonauts-cli commands            │
                          └────────────────────┬────────────────────────┘
                                               │
          ┌────────────────────────────────────▼──────────────────────────────────────┐
          │                        assistonauts-core                                   │
          │                                                                            │
          │  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐        │
          │  │ Captain  │ │  Scout   │ │ Compiler │ │ Curator  │ │ Explorer │        │
          │  │ (plan +  │ │ (ingest) │ │ (compile)│ │ (link)   │ │ (query)  │        │
          │  │  triage) │ │          │ │          │ │          │ │          │        │
          │  └────┬─────┘ └────┬─────┘ └────┬─────┘ └────┬─────┘ └────┬─────┘        │
          │       │            │            │            │            │               │
          │       │     ┌──────▼────────────▼────────────▼────────────▼──────┐        │
          │       │     │              Base Agent Class                       │        │
          │       │     │  toolkit | llm_client | cache | owned_dirs         │        │
          │       │     └──────────────────┬─────────────────────────────────┘        │
          │       │                        │                                          │
          │  ┌────▼────────────────────────▼─────────────────────────────────┐        │
          │  │                    Shared Infrastructure                       │        │
          │  │                                                               │        │
          │  │  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────────┐ │        │
          │  │  │ LLM      │  │ Config   │  │ Cache    │  │ Task         │ │        │
          │  │  │ Client   │  │ Loader   │  │ Layers   │  │ Runner       │ │        │
          │  │  │ (litellm)│  │ (YAML)   │  │ (3-tier) │  │ (exec+track) │ │        │
          │  │  └──────────┘  └──────────┘  └──────────┘  └──────────────┘ │        │
          │  │                                                               │        │
          │  │  ┌──────────┐  ┌──────────────────────────────────────────┐  │        │
          │  │  │ Storage  │  │ Archivist System (deterministic, no LLM) │  │        │
          │  │  │ (file IO │  │ embeddings | FTS | vector | manifest    │  │        │
          │  │  │  + owns) │  │ summaries | reranking | retrieval       │  │        │
          │  │  └──────────┘  └──────────────────────────────────────────┘  │        │
          │  └───────────────────────────────────────────────────────────────┘        │
          │       │                                                                    │
          │       │     ┌──────────────────────────────────────────────┐              │
          │       └────►│ Inspector (validate, no direct edits)        │              │
          │             └──────────────────────────────────────────────┘              │
          └────────────────────────────────────────────────────────────────────────────┘
                                               │
                          ┌────────────────────▼────────────────────────┐
                          │              Workspace (filesystem)          │
                          │  raw/ | wiki/ | index/ | audits/            │
                          │  expeditions/ | station-logs/ | .assistonauts/│
                          └─────────────────────────────────────────────┘
```

**Data flow (build phase):**

1. Scout ingests sources → writes to `raw/`
2. Compiler reads `raw/`, writes articles + content summaries → `wiki/`
3. Archivist indexes articles → `index/` (embeddings, FTS, manifest, summaries)
4. Curator reads via Archivist retrieval, writes backlinks → `wiki/` (link sections only)
5. Inspector reads `wiki/` + `index/manifest.json`, writes findings → `audits/`
6. Captain orchestrates all of the above, writes plans/logs → `expeditions/`, `station-logs/`
7. Explorer reads via Archivist retrieval, writes explorations → `wiki/explorations/`

---

## Phase 1 — Core Infrastructure + Scout Architecture

### Package Structure

```
assistonauts-core/
├── pyproject.toml              # uv/pip project config, scripts, dependencies
├── src/
│   └── assistonauts/
│       ├── __init__.py
│       ├── __main__.py         # CLI entry point
│       ├── cli/
│       │   ├── __init__.py
│       │   ├── main.py         # Click group, top-level commands
│       │   └── scout.py        # scout subcommands
│       ├── agents/
│       │   ├── __init__.py
│       │   ├── base.py         # Base Agent class
│       │   └── scout.py        # Scout agent implementation
│       ├── tools/
│       │   ├── __init__.py
│       │   ├── shared.py       # Logger, config reader, cache interface, file I/O
│       │   └── scout.py        # Format converters, web clipper, hasher, dedup
│       ├── llm/
│       │   ├── __init__.py
│       │   └── client.py       # litellm wrapper with record/replay
│       ├── config/
│       │   ├── __init__.py
│       │   └── loader.py       # YAML config parsing and validation
│       ├── cache/
│       │   ├── __init__.py
│       │   └── content.py      # Content hash cache (manifest)
│       ├── storage/
│       │   ├── __init__.py
│       │   └── workspace.py    # Workspace init, directory management, ownership
│       └── models/
│           ├── __init__.py
│           └── config.py       # Pydantic/dataclass models for configs
├── tests/
│   ├── conftest.py             # Shared fixtures, replay client setup
│   ├── fixtures/               # Recorded LLM response fixtures
│   │   └── scout/
│   ├── unit/
│   │   ├── test_config_loader.py
│   │   ├── test_workspace.py
│   │   ├── test_manifest.py
│   │   ├── test_llm_client.py
│   │   └── test_scout_tools.py
│   └── contract/
│       └── test_scout_output.py
└── .assistonauts/              # Runtime config (created by `init`)
```

### Base Agent Class

```python
from pathlib import Path
from dataclasses import dataclass, field

@dataclass
class Agent:
    """Base class for all Assistonauts agents."""
    role: str
    system_prompt: str
    toolkit: dict[str, callable]     # name → deterministic tool function
    llm_client: LLMClient            # injected, supports record/replay
    cache: CacheInterface             # shared cache layers
    owned_dirs: list[Path]            # directories this agent can write to
    readable_dirs: list[Path]         # directories this agent can read from
    logger: StructuredLogger          # structured logging per mission

    def run_mission(self, mission: Mission) -> MissionResult:
        """Execute a mission. Subclasses implement the agent-specific logic."""
        raise NotImplementedError

    def _read_file(self, path: Path) -> str:
        """Read a file, enforcing readable_dirs boundary."""
        ...

    def _write_file(self, path: Path, content: str) -> None:
        """Write a file, enforcing owned_dirs boundary."""
        ...

    def _call_llm(self, messages: list[dict], **kwargs) -> str:
        """Call LLM via the injected client. Records/replays in test mode."""
        ...
```

Key design constraints:

- **LLM client is injected, not constructed** — tests swap in a replay client without monkey-patching
- **Toolkit methods are plain functions** — independently testable, no LLM, no side effects beyond file I/O
- **Ownership enforcement is in the base class** — agents cannot accidentally write to directories they don't own
- **Structured logging** — every LLM call and tool invocation is logged with timestamps, token counts, and mission context

### LLM Client

```python
class LLMClient:
    """Provider-agnostic LLM wrapper with record/replay for testing."""

    def __init__(
        self,
        provider_config: dict,         # role-to-provider mapping
        mode: str = "live",            # "live" | "record" | "replay"
        fixture_dir: Path | None = None,
    ):
        ...

    def complete(
        self,
        messages: list[dict],
        model: str | None = None,      # override role default
        system: str | None = None,
        **kwargs,
    ) -> LLMResponse:
        """Make an inference call. In replay mode, returns cached response."""
        ...
```

- `live` mode: calls litellm, no caching
- `record` mode: calls litellm, saves request/response pairs to `fixture_dir`
- `replay` mode: returns saved responses keyed by `SHA-256(model + system + messages)`, no API calls
- Stale fixture detection: hash the system prompt, warn if prompt changed since fixture was recorded

### Config System

```yaml
# .assistonauts/config.yaml — global settings
llm:
  providers:
    anthropic:
      model: claude-sonnet-4-20250514
      api_key_env: ANTHROPIC_API_KEY
    ollama:
      model: llama3.2
      base_url: http://localhost:11434
  roles:
    captain: anthropic
    scout: ollama
    compiler: anthropic
    curator: anthropic
    inspector: anthropic
    explorer: anthropic

embedding:
  active: ollama
  providers:
    ollama:
      model: nomic-embed-text
      base_url: http://localhost:11434

cache:
  llm_responses:
    enabled: true
    backend: sqlite
    ttl_hours: 168
    max_size_mb: 500
```

```yaml
# expeditions/<name>/expedition.yaml — per-expedition config
expedition:
  name: autotrader-research
  description: "Research knowledge base for BTC/USD prediction system"
  phase: build
  scope:
    description: >
      Machine learning approaches to cryptocurrency price prediction
    keywords: [ML, trading, BTC, regime detection]
  sources:
    local:
      - path: ~/research/papers/
        pattern: "*.pdf"
```

Config models are validated with dataclasses (or Pydantic if warranted by complexity). Unknown keys warn, missing required keys error.

### Content Hash Cache (Manifest)

```json
// index/manifest.json
{
  "raw/papers/fft-analysis.md": {
    "hash": "a3f2e8...",
    "last_processed": "2026-04-05T12:00:00Z",
    "processed_by": "scout",
    "downstream": ["wiki/concepts/spectral-analysis.md"]
  }
}
```

- SHA-256 of file contents
- Checked before any agent processes a file — if hash matches, operation is skipped
- `downstream` array tracks which wiki articles depend on each raw source (populated by Compiler in Phase 2)
- Atomic writes via write-to-temp-then-rename to prevent corruption

### Scout Agent

The Scout follows the standard agent pattern: toolkit scan → LLM reasoning → toolkit execution.

**Ingestion pipeline:**

1. Receive input path or URL
2. Content hasher checks manifest — skip if unchanged
3. Dedup checker runs simhash against existing `raw/` files — warn if near-duplicate
4. Format converter transforms to markdown (markitdown for PDF/HTML/DOCX, web clipper for URLs)
5. Assets (images, diagrams) downloaded to `raw/assets/` with local references in markdown
6. If expedition scope is configured: keyword relevance filter (deterministic), optional LLM relevance check for borderline items
7. Write markdown to `raw/<category>/`, update manifest

**Toolkit functions (all deterministic, independently testable):**

- `convert_pdf(path) → str` — PDF to markdown via markitdown
- `convert_html(path_or_url) → str` — HTML to markdown
- `clip_web(url) → tuple[str, list[Path]]` — fetch URL, extract content, download assets
- `hash_content(path) → str` — SHA-256
- `check_dedup(content_hash, manifest) → list[Match]` — simhash/minhash near-duplicate check
- `check_relevance_keywords(text, keywords) → float` — keyword overlap score

### Workspace Initialization

`assistonauts init` creates:

```
workspace/
├── .git/                          # git init
├── .gitignore                     # ignore derived data (see below)
├── raw/
│   ├── papers/
│   ├── articles/
│   ├── repos/
│   ├── datasets/
│   └── assets/
├── wiki/
│   ├── concepts/
│   ├── entities/
│   ├── logs/
│   └── explorations/
├── index/
│   └── manifest.json              # empty: {}
├── audits/
│   └── findings/
├── expeditions/
├── station-logs/
└── .assistonauts/
    ├── config.yaml                # default config (user edits)
    ├── agents/                    # agent role definitions
    ├── cache/
    └── hooks/
```

`.gitignore` includes:

```
.assistonauts/cache/
index/assistonauts.db
__pycache__/
*.pyc
.env
```

### Key Architectural Decisions

- **No heavyweight frameworks (LangChain, LlamaIndex).** The orchestration and toolkits are simple enough to own entirely. This avoids framework lock-in and keeps the dependency tree shallow.
- **litellm for provider abstraction.** Single wrapper supporting Claude, OpenAI, Ollama, Vertex, etc. Role-to-provider mapping allows mixing models (cheap Ollama for Scout, frontier Claude for Captain).
- **Injectable LLM client with record/replay.** Shapes the entire testing strategy. Every agent can be tested with deterministic fixture replay, no API calls needed.
- **Ownership enforcement in base class.** Prevents agents from writing to directories they don't own. This is application-level enforcement (not OS-level), but it catches bugs early and maintains the architectural boundary.
- **Manifest as JSON, not SQLite.** The manifest is human-readable, git-trackable, and simple. It will grow with the knowledge base but remains manageable at the expected scale (hundreds to low thousands of entries). If it becomes a bottleneck, migration to SQLite is straightforward.
- **Workspace is git-tracked from init.** Mission-level commits provide audit trail, rollback, and a readable log of agent activity.

### Testing Approach

- **Unit tests** for config loading, manifest operations, workspace init, each Scout toolkit function
- **Contract tests** for Scout agent output — replay a recorded LLM fixture, assert output structure (valid markdown, frontmatter present, assets referenced correctly)
- **conftest.py** provides shared fixtures: temporary workspace, replay LLM client, sample source documents

### Deployment

Phase 1 is CLI-only, installed via `pip install -e .` (or `uv pip install -e .`) during development. The `assistonauts` command is registered as a console script entry point in `pyproject.toml`.

```toml
[project.scripts]
assistonauts = "assistonauts.cli.main:cli"
```

### Phase 1 Dependencies

```toml
[project]
requires-python = ">=3.11"
dependencies = [
    "litellm",
    "pyyaml",
    "click",
    "rich",
    "markitdown",
]

[project.optional-dependencies]
dev = [
    "pytest",
    "pytest-cov",
    "ruff",
]
```

Note: `sqlite-vec`, `feedparser`, `watchdog`, and `fastapi` are deferred to the phases that need them.

---

## Phase 2+ — Architecture Stubs

_Expand these sections as each phase approaches. Keep them minimal until the phase is active — detailed architecture written too early becomes stale._

### Phase 2 — Compiler + Task Runner

Wiki schema template system and Compiler agent added to `agents/compiler.py` and `tools/compiler.py`. Task runner (`tasks/runner.py`, currently `missions/runner.py` pending rename) executes single tasks with YAML audit trail, failure classification (transient vs deterministic), and task-level git commits. Compiler plan mode (`compiler.plan()`) provides editorial triage — analyzes raw sources and proposes compilation tasks with article types, source groupings, and titles. CLI gains `task run` command (currently `mission run` pending rename).

### Phase 3 — Archivist System + Curator + Hybrid RAG

Archivist system (`archivist/`) as a deterministic service — not an agent. sqlite-vec + FTS5 hybrid retrieval in `index/assistonauts.db`. Multi-pass retrieval module (`rag/multi_pass.py`) shared by Curator and Explorer. Curator agent (`agents/curator.py`) as singleton for cross-referencing. Embedding and LLM response caches added to `cache/`. Three new dependencies: `sqlite-vec`, `numpy` (for embeddings).

### Phase 4 — Explorer + Interactive Mode

Explorer agent (`agents/explorer.py`) with query flow via multi-pass retrieval. Interactive REPL session via Click. Exploration filing to `wiki/explorations/`. Output renderer for markdown, slides (Marp), and charts (matplotlib). New optional dependency: `matplotlib`.

### Phase 5 — Captain + Expedition Orchestration

Captain agent (`agents/captain.py`) with planning and operations modes. Creates missions (multi-step objectives) that decompose into ordered task sequences. Mission ledger (`ledger.db`) in SQLite for mission-level state persistence; individual tasks use YAML audit trails from the Phase 2 task runner. Task queue manager with dependency graph and topological sort. Captain delegates editorial decisions (article types, groupings, titles) to Compiler plan mode. Deterministic scaling system for concurrent agent instances. Budget tracking system. Expedition lifecycle orchestration.

### Phase 6 — Inspector + Quality + Review

Inspector agent (`agents/inspector.py`) with deterministic-scan-first sweep pattern. Full toolkit for mechanical checks (links, orphans, staleness, duplicates, schema, freshness). Audit report generation. Finding → Compiler fix task pipeline. Human review queue with typed items and Captain grouping. Exploration promotion pipeline. Summary quality validation — first sweep anticipates remediation batch.

### Phase 7 — Stationed Mode

Watch system (`watchdog` for files, `feedparser` for RSS, GitHub API poller, web change detection). Event/trigger system mapping events to Captain mission routing. Cron-based scheduling. Station log generation with health metrics. Cycle guards. Pause/resume. New dependencies: `watchdog`, `feedparser`.
