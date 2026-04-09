# Assistonauts

## Project Identity

Assistonauts is a framework for building and maintaining LLM-powered knowledge bases using specialized AI agents. It targets developers and teams who need structured, interlinked, continuously maintained knowledge wikis from diverse source material (papers, articles, repos, datasets). What makes it distinctive: knowledge is compiled once and kept current by stationed agents, using RAG only for routing rather than rediscovering knowledge from scratch on every query.

## Tech Stack

- **Language:** Python 3.11+, strict typing (no `Any` without justification)
- **CLI Framework:** Click + Rich
- **LLM:** litellm (provider-agnostic — Claude, OpenAI, Ollama, Vertex)
- **Database:** SQLite (FTS5 for keyword search, sqlite-vec for vector similarity, task audit trails, LLM cache)
- **Testing:** pytest + pytest-cov, contract tests with recorded LLM fixtures
- **Linter/Formatter:** ruff (lint + format)
- **Package Manager:** uv
- **Hosting:** CLI-only for v1 (local execution). Server deployment (FastAPI) deferred
- **Key Dependencies:** litellm, pyyaml, click, rich, markitdown, sqlite-vec, Pillow, watchdog, feedparser
- **No heavyweight frameworks** — no LangChain, no LlamaIndex

## Current Phase

**Phase 5 — Captain + Expedition Orchestration** (Phase 5 complete, pending merge)

See `docs/REQUIREMENTS.md` for the full development plan.
See `docs/ARCHITECTURE.md` for technical architecture details.
See `docs/PHASE_STATUS.md` for current completion state.

Do not implement features from future phases. If you encounter a dependency on a future phase, note it in your session handoff and move on. Fixes and improvements to prior phase deliverables are not restricted. If the current phase's work reveals a bug, gap, or quality issue in an earlier phase's deliverable, fix it — these are refinements to completed work, not scope creep. Use /change to classify and route appropriately.

Do not modify sections of this file during active development. CLAUDE.md updates happen during /handoff via the freshness check — the agent proposes changes and the user approves. This prevents mid-session drift while keeping the file current.

## Directory Structure

```
assistonauts/
├── CLAUDE.md                       # This file — project context for Claude Code
├── pyproject.toml                  # Project config, dependencies, scripts
├── docs/
│   ├── REQUIREMENTS.md             # Full development plan
│   ├── ARCHITECTURE.md             # Technical architecture
│   ├── PHASE_STATUS.md             # Living phase completion tracker
│   ├── assistonauts-spec.md        # Original product spec
│   ├── sessions/                   # Session handoff artifacts
│   └── uat/                        # Phase UAT scripts
├── src/
│   └── assistonauts/
│       ├── __init__.py
│       ├── __main__.py             # CLI entry point
│       ├── cli/                    # Click command groups
│       ├── agents/                 # Agent implementations (base + per-role)
│       ├── tools/                  # Deterministic agent toolkits
│       ├── llm/                    # litellm wrapper with record/replay
│       ├── config/                 # YAML config loading and validation
│       ├── cache/                  # Cache layers (content, LLM, embedding)
│       ├── storage/                # Workspace management, file I/O, ownership
│       ├── archivist/              # Knowledge base OS (Phase 3)
│       ├── tasks/                  # Task runner, state machine (Phase 2)
│       ├── missions/               # Mission model, state machine, dependencies (Phase 5)
│       ├── expeditions/            # Expedition lifecycle, orchestrator, scaling, budget (Phase 5)
│       ├── rag/                    # Multi-pass retrieval (Phase 3)
│       └── models/                 # Data models (configs, tasks, etc.)
├── tests/
│   ├── conftest.py                 # Shared fixtures, replay client setup
│   ├── helpers.py                  # FakeLLMClient, FakeEmbeddingClient (canonical source)
│   ├── fixtures/                   # Recorded LLM response fixtures
│   ├── unit/                       # Unit tests for toolkit functions
│   └── contract/                   # Contract tests for agent output structure
├── .claude/                        # Claude Code configuration
│   ├── settings.json
│   ├── agents/
│   ├── commands/
│   └── skills/
└── sandbox/                        # Docker sandbox for autonomous mode
```

## Testing

### First, Run the Tests

At the start of every session, before doing anything else, run:

```
pytest
```

This anchors you in the current state of the codebase. It tells you how many tests exist, whether anything is broken, and puts you in a testing mindset for the session.

### Red/Green TDD

Use red/green TDD for every feature:

1. **Write the test first** — define what the feature should do
2. **Run the test and watch it fail** (red) — confirm the test is actually testing something
3. **Implement the minimum code to make it pass** (green)
4. **Refactor** if needed, re-running tests to confirm nothing breaks

This is non-negotiable. Every new feature, component, utility function, API route, and event handler gets a test written before the implementation.

### Test Commands

```bash
pytest                         # Run all tests
pytest --watch                 # Watch mode during development (requires pytest-watch)
pytest --cov=assistonauts      # Coverage report
```

### Testing LLM-Driven Behavior

Agents make LLM calls that produce non-deterministic output. Three testing layers handle this:

1. **Contract tests** — assert on output _structure_ (valid frontmatter, required sections, citations present) using recorded fixtures. Primary test layer, runs on every commit.
2. **Recorded fixtures** — captured LLM responses replayed via `LLMClient(mode="replay")`. Makes contract tests fast and deterministic.
3. **Integration tests** — real LLM calls against a fixture corpus. Expensive, run manually or on schedule, not on every commit.

See the Testing Strategy section in `docs/assistonauts-spec.md` for full details.

### Test Helpers

`tests/helpers.py` is the canonical source for fake test infrastructure. Import from here — do not define local copies in test files.

- **`FakeLLMClient`** — returns canned responses, tracks calls. Use for unit tests.
- **`FakeEmbeddingClient`** — deterministic SHA-256-based embeddings. Use for testing Archivist/retrieval without a real embedding model.

## Coding Standards

### General

- Strict type hints everywhere. No `Any` types. No `type: ignore` without a comment explaining why.
- All async operations must have error handling. No unhandled exceptions in agent code.
- Use descriptive names. Clarity over brevity.
- Prefer dataclasses for data models. Use Pydantic only if runtime validation justifies the dependency.
- Imports: standard library, then third-party, then local — separated by blank lines. Use absolute imports from the `assistonauts` package.
- No mutable default arguments.
- Functions over classes when there's no state to manage. Toolkit functions are plain functions, not methods on a toolkit class.

### Error Handling

- CLI errors show a meaningful message via Rich. Technical details go to the structured log.
- Agent errors are classified as transient or deterministic (see task runner). Transient errors retry; deterministic errors fail-fast to the review queue.
- File I/O errors from ownership boundary violations raise `OwnershipError` with the agent role, attempted path, and allowed directories.

## Git Conventions

### Commit Frequency

Commit after each completed feature or meaningful unit of work within a session. Small, frequent commits with descriptive messages. Each commit should leave the codebase in a working state (tests pass).

### Commit Messages

Use conventional commits format:

```
feat(component): add new feature
fix(module): correct specific bug
test(feature): add red/green tests for feature
docs(section): update documentation
chore(deps): upgrade dependency
refactor(module): restructure without behavior change
```

### Branching

- `main` — production-ready code
- `phase/1-core-infrastructure-scout` — Phase 1
- `phase/2-compiler-mission-runner` — Phase 2
- `phase/3-archivist-curator-rag` — Phase 3
- `phase/4-explorer-interactive` — Phase 4
- `phase/5-captain-orchestration` — Phase 5
- `phase/6-inspector-quality-review` — Phase 6
- `phase/7-stationed-mode` — Phase 7
- `feat/description` — feature branches off the phase branch for larger features
- Merge feature branches into the phase branch. Merge the phase branch into `main` when the phase is complete and evaluated.

### Session Context from Git

When resuming work, reviewing recent git history is a fast way to rebuild context:

```
git log --oneline -20
```

This is complementary to reading the session handoff artifact — use git log for quick orientation, read the handoff doc for detailed state.

## Session Workflow

### Starting a Session

1. **Run the tests:** `pytest` — establish baseline
2. **Load context:** Read `docs/PHASE_STATUS.md` and the latest file in `docs/sessions/`
3. **Review recent changes:** `git log --oneline -10` to orient on recent work
4. **Plan:** Identify the next feature to implement within the current phase. State what you'll build and how you'll test it before writing code

### During a Session

- Work on **one feature at a time**. Complete it (including tests) before starting the next
- **After each completed feature, run a self-check:**
  1. `pytest` — all tests pass, no regressions
  2. `ruff check src/` — no lint errors
  3. `ruff format --check src/` — formatting is clean
  4. Verify: no `Any` types introduced, no TODO/FIXME left unresolved, no stubbed implementations
  5. If any check fails, fix before moving to the next feature
- Commit after each completed feature (after the self-check passes)
- If you encounter a decision point with multiple valid approaches, pause and explain the tradeoffs. Do not pick one silently

### Ending a Session

- **Invoke the evaluator subagent** (`@evaluator`) for an independent QA assessment of all work completed this session. Present the evaluator's full report without softening or editorializing. If the evaluator returns a FAIL verdict, address the critical issues before proceeding to handoff. You can also invoke `/evaluate` manually mid-session on specific features if you want earlier feedback
- Run the full test suite one final time
- Commit any uncommitted work
- Generate a session handoff artifact at `docs/sessions/session-YYYY-MM-DD-NNN.md` containing:
  - **Completed:** what was built this session, with commit references
  - **In Progress:** anything started but not finished
  - **Blocked:** anything that can't proceed and why
  - **Evaluator Results:** summary of the evaluator's scores and any unresolved issues
  - **Test State:** number of tests, all passing/any failing
  - **Next Steps:** the logical next feature(s) to tackle
- Update `docs/PHASE_STATUS.md` with current completion state

### Session Artifact Conventions

When **writing** handoff artifacts, be concrete: include commit hashes, test counts, specific file paths. Don't omit problems — if you cut a corner or stubbed something, say so. Keep "Next Steps" specific enough to start implementing immediately.

When **reading** handoff artifacts, prioritize: In Progress → Blocked → Next Steps → Evaluator Results. These determine what happens next. If unresolved critical issues from the evaluator exist, address those before new feature work.

When **updating PHASE_STATUS.md**, use the format: `✅ YYYY-MM-DD, session-YYYY-MM-DD-NNN` for completed deliverables. Update the "Last updated" header line with the current date and session reference. See `.claude/skills/session-management/SKILL.md` for additional conventions on context continuity patterns across different gap durations.

## References

- `docs/REQUIREMENTS.md` — full development plan with deliverables and dependencies
- `docs/ARCHITECTURE.md` — technical architecture and data flow specifications
- `docs/PHASE_STATUS.md` — living tracker of phase completion
- `docs/assistonauts-spec.md` — original product spec (source of truth for agent behavior, data architecture, and system design)
- `docs/sessions/` — session handoff artifacts with detailed state from prior work sessions
- `.claude/agents/evaluator.md` — QA/evaluator subagent for post-feature evaluation
- `.claude/commands/` — session workflow commands (`/start-phase`, `/evaluate`, `/handoff`, `/status`)
- `.claude/settings.json` — project-level permissions and hooks (committed to git, shared)
- `.claude/settings.local.json` — personal permission overrides (gitignored). Use this for machine-specific settings. Local scope overrides project scope
- `.claude/hooks/` — deterministic enforcement scripts (bash-guard, auto-format, stop-check)
- `sandbox/` — Docker sandbox for running Claude Code with `--dangerously-skip-permissions`

### Security Model

Permissions, hooks, and the Docker sandbox form three layers of defense:

1. **Permissions** (settings.json) — auto-allow safe commands, auto-deny known-bad patterns. Convenience layer — reduces permission prompts for routine work
2. **Hooks** (bash-guard.sh) — deterministic enforcement of dangerous patterns. Works both inside and outside Docker. Blocks destructive commands, git push, gcloud delete operations
3. **Docker sandbox** (optional) — network-level isolation via iptables firewall. Blocks all non-allowlisted outbound traffic. Only needed for `--dangerously-skip-permissions` mode

The Write and Edit permissions in settings.json are scoped to project directories. If you need to write to an unlisted path, add it to `.claude/settings.local.json`.
