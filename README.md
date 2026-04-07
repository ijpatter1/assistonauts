# Assistonauts

A framework for building and maintaining LLM-powered knowledge bases using specialized AI agents. Raw source material — papers, articles, repos, datasets, images — is ingested, compiled into a structured interlinked markdown wiki, indexed for hybrid retrieval, quality-checked for integrity, and continuously maintained by a team of stationed agents.

## Core Idea

Traditional RAG rediscovers knowledge from scratch on every query. Assistonauts compiles knowledge once, keeps it current, and uses RAG only for routing — finding which compiled articles are relevant — while the LLM reasons over full, structured documents.

## Architecture

Six specialized agents supported by a deterministic knowledge base operating system:

| Agent         | Role                                                      | Scalable  |
| ------------- | --------------------------------------------------------- | --------- |
| **Captain**   | Expedition planning, mission orchestration, triage        | Singleton |
| **Scout**     | Source ingestion — PDF, HTML, web, RSS, repos to markdown | Yes       |
| **Compiler**  | Synthesis — raw sources into structured wiki articles     | Yes       |
| **Curator**   | Cross-referencing, backlinks, structural stewardship      | Singleton |
| **Inspector** | Quality validation, contradiction detection, audits       | Singleton |
| **Explorer**  | Query synthesis, interactive Q&A, research missions       | Yes       |

The **Archivist** is not an agent — it's the deterministic operating system of the knowledge base: embedding generation, FTS indexing, hybrid retrieval, manifest tracking. No LLM inference.

## Tech Stack

- **Python 3.12+** with strict typing
- **litellm** for provider-agnostic LLM calls (Claude, OpenAI, Ollama, Vertex)
- **SQLite** — FTS5 for keyword search, sqlite-vec for vector similarity, mission ledger
- **Click + Rich** for CLI
- **No heavyweight frameworks** — no LangChain, no LlamaIndex

## Development Phases

| Phase | Name                                    | Status      |
| ----- | --------------------------------------- | ----------- |
| 1     | Core Infrastructure + Scout             | Not started |
| 2     | Compiler + Mission Runner               | Not started |
| 3     | Archivist System + Curator + Hybrid RAG | Not started |
| 4     | Explorer + Interactive Mode             | Not started |
| 5     | Captain + Expedition Orchestration      | Not started |
| 6     | Inspector + Quality + Review            | Not started |
| 7     | Stationed Mode                          | Not started |

See `docs/REQUIREMENTS.md` for the full development plan and `docs/assistonauts-spec.md` for the product spec.

## Getting Started

```bash
# Install dependencies
uv pip install -e ".[dev]"

# Run tests
pytest

# Start Phase 1 development (in Claude Code)
/start-phase 1
```

## Development Environment

This repo includes a Docker sandbox for autonomous Claude Code sessions, session management commands, and a QA evaluator subagent. See the `sandbox/` directory and `.claude/` configuration for details.

| Command        | Description                              |
| -------------- | ---------------------------------------- |
| `make sandbox` | Build + start Claude Code in Docker      |
| `make attach`  | Reattach to running sandbox after crash  |
| `make shell`   | Bash shell in sandbox for debugging      |
| `make dev`     | Run dev server on host                   |
| `make clean`   | Remove container + image (keeps volumes) |

## Project Structure

```
├── CLAUDE.md                    # Project context for Claude Code
├── docs/
│   ├── assistonauts-spec.md     # Product spec (source of truth)
│   ├── REQUIREMENTS.md          # Development plan — 7 phases, 67 deliverables
│   ├── ARCHITECTURE.md          # Technical architecture
│   ├── PHASE_STATUS.md          # Deliverable tracker
│   └── sessions/                # Session handoff artifacts
├── src/
│   └── assistonauts/            # Core engine
│       ├── agents/              # Agent implementations
│       ├── tools/               # Deterministic agent toolkits
│       ├── llm/                 # litellm wrapper with record/replay
│       ├── archivist/           # Knowledge base OS
│       ├── rag/                 # Multi-pass retrieval
│       ├── missions/            # Mission runner + state machine
│       └── cli/                 # Click commands
├── tests/                       # pytest suite
├── .claude/                     # Claude Code config, hooks, commands
└── sandbox/                     # Docker sandbox for autonomous mode
```
