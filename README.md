# Claude Code Development Environment

A ready-to-use development environment for autonomous Claude Code sessions with built-in QA evaluation, session management, and Docker sandboxing.

Based on patterns from [Anthropic's harness design research](https://www.anthropic.com/engineering/harness-design-long-running-apps) and [Simon Willison's Agentic Engineering Patterns](https://simonwillison.net/guides/agentic-engineering-patterns/).

## What's Included

**Session workflow** — Commands that encode a Planner → Generator → Evaluator loop:
- `/start-phase N` — Load context, run tests, present a plan for approval
- `/evaluate` — Trigger independent QA evaluation mid-session
- `/handoff` — End session with full QA + handoff artifact for continuity
- `/status` — Quick 10-line project orientation

**QA evaluator subagent** — An independent, skeptical reviewer that grades work on five criteria (Functionality, Test Quality, Code Quality, Completeness, Integration). Runs in its own context window with read-only enforcement. Auto-invoked before every session handoff.

**Docker sandbox** — Isolated container for `--dangerously-skip-permissions` mode with iptables firewall, non-root execution, and domain allowlisting. Optional — works without Docker too.

**Safety hooks** — Deterministic enforcement of dangerous command blocking (bash-guard), auto-formatting (auto-format), and session reminder (stop-check).

**Session continuity** — Handoff artifacts and phase status tracking that carry context across sessions and context resets.

## Quick Start

### 1. Create a new repo from this template

Click **"Use this template"** on GitHub, or:

```bash
git clone https://github.com/YOUR_USERNAME/claude-code-env.git my-project
cd my-project
rm -rf .git && git init
```

### 2. Configure for your project

The fastest path — give Claude Code your spec:

```bash
# Start Claude Code (native or sandbox)
claude
# or: make sandbox

# Point it at your PRD/spec
/init-project path/to/your-spec.md
```

This reads your spec and generates all four project-specific files:
- `CLAUDE.md` — project identity, tech stack, coding standards
- `docs/REQUIREMENTS.md` — phases and deliverables extracted from your spec
- `docs/ARCHITECTURE.md` — Phase 1 detailed architecture, later phases stubbed
- `docs/PHASE_STATUS.md` — deliverable tracker matching REQUIREMENTS.md

Review the generated files, adjust anything that needs it, then commit and start building.

**Manual alternative** — edit the four template files directly:
- **`CLAUDE.md`** — Fill in tech stack, project identity, coding standards, bootstrapping
- **`docs/REQUIREMENTS.md`** — Define your phases and deliverables
- **`docs/ARCHITECTURE.md`** — Document your technical architecture
- **`docs/PHASE_STATUS.md`** — Copy deliverables from REQUIREMENTS.md with ⬜ markers

Either way, also update:
- **`Makefile`** — Change `IMAGE_NAME` and `CONTAINER_NAME` at the top (two lines)

Optionally customize:

- **`sandbox/init-firewall.sh`** — Add project-specific domains to `PROJECT_DOMAINS`
- **`.claude/settings.json`** — Add project-specific Write/Edit paths if your directory structure differs from `src/`, `tests/`, `docs/`, `public/`

### 3. Set your API key

```bash
echo 'export ANTHROPIC_API_KEY=sk-ant-...' >> ~/.zshrc
source ~/.zshrc
```

### 4. Start coding

```bash
# Option A: Docker sandbox (autonomous, no permission prompts)
make sandbox

# Option B: Native Claude Code (interactive, with Remote Control)
claude
```

Then inside Claude Code:

```
/start-phase 1
```

### 5. Daily workflow

```bash
# Terminal 1: Claude Code
make sandbox
# /start-phase 1

# Terminal 2: Dev server on your Mac
make dev

# Terminal 3: Your tools (VS Code, git, tests)
code .
```

## File Structure

```
├── CLAUDE.md                          # Project context (YOU EDIT THIS)
├── Makefile                           # Container lifecycle
├── .gitignore                         # Git exclusions
├── .claude/
│   ├── settings.json                  # Permissions + hooks
│   ├── settings.local.json            # Personal overrides (gitignored)
│   ├── agents/
│   │   └── evaluator.md               # QA evaluator subagent
│   ├── commands/
│   │   ├── init-project.md            # Scaffold docs from a PRD/spec
│   │   ├── start-phase.md             # Session initialization
│   │   ├── evaluate.md                # Manual evaluation trigger
│   │   ├── handoff.md                 # Session end + QA + handoff
│   │   └── status.md                  # Quick status check
│   ├── hooks/
│   │   ├── bash-guard.sh              # Blocks dangerous commands
│   │   ├── auto-format.sh             # Auto-formats on write
│   │   └── stop-check.sh              # Reminds about evaluation
│   └── skills/
│       └── session-management/
│           └── SKILL.md               # Context continuity conventions
├── docs/
│   ├── REQUIREMENTS.md                # Development plan (YOU EDIT THIS)
│   ├── ARCHITECTURE.md                # Technical architecture (YOU EDIT THIS)
│   ├── PHASE_STATUS.md                # Phase tracker (YOU EDIT THIS)
│   └── sessions/
│       └── .gitkeep
└── sandbox/
    ├── Dockerfile                     # Sandbox image
    ├── init-firewall.sh               # Domain allowlist firewall
    ├── entrypoint.sh                  # Privilege drop + Claude start
    └── README.md                      # Sandbox documentation
```

Files marked **(YOU EDIT THIS)** are project-specific templates. Everything else works out of the box.

## GCP Access (Optional)

If your project uses Google Cloud:

```bash
make gcp-setup    # Prints step-by-step instructions
```

## Commands Reference

| Command | Description |
|---------|-------------|
| `make sandbox` | Build + start Claude Code in Docker |
| `make attach` | Reattach to running sandbox after crash |
| `make shell` | Bash shell in sandbox for debugging |
| `make prompt P="..."` | Run a one-shot headless prompt |
| `make resume S="name"` | Resume a named session |
| `make dev` | Run dev server on host |
| `make stop` | Stop the sandbox container |
| `make clean` | Remove container + image (keeps volumes) |
| `make clean-all` | Full reset including auth and sessions |
| `make gcp-setup` | Print GCP service account instructions |
| `make test-fw` | Verify firewall blocks correctly |

## Origins

This environment encodes three key patterns:

1. **Separated evaluation** (from [Anthropic's harness research](https://www.anthropic.com/engineering/harness-design-long-running-apps)) — The evaluator subagent runs in its own context with read-only access, preventing the self-praise problem where agents rate their own work too generously.

2. **Test-first anchoring** (from [Simon Willison's Agentic Engineering Patterns](https://simonwillison.net/guides/agentic-engineering-patterns/)) — Every session starts by running the test suite. Every feature uses red/green TDD. Tests are the regression safety net across phases.

3. **Structured handoffs** (from both sources) — Session artifacts carry enough context for a clean restart, avoiding the quality degradation that comes from context window growth and compaction.
