#!/bin/bash
# ═══════════════════════════════════════════════════════
# Push Phase 4 Branch and Create PR
# Created: 2026-04-09, session-2026-04-09-003
# Phase: 4
# Blocks: Phase 5 start (Captain + Expedition Orchestration)
#
# Phase 4 (Explorer + Interactive Mode) was fully implemented
# inside the sandbox across 6 commits on phase/4-explorer-interactive.
# All 7 deliverables are complete: Explorer agent, toolkit (citation
# formatter, context budget, Marp/chart renderers), exploration filing,
# interactive REPL with conversational flow, contract tests with
# recorded fixtures, and the assistonauts explore CLI command.
#
# Usage: bash docs/manual/task-2026-04-09-003.sh
# ═══════════════════════════════════════════════════════
set -euo pipefail

# ── User Configuration ───────────────────────────────

BRANCH="phase/4-explorer-interactive"
BASE_BRANCH="main"
REPO_ROOT="$(git rev-parse --show-toplevel 2>/dev/null || echo ".")"

# ── Prerequisites ────────────────────────────────────

check_prereq() {
  command -v "$1" >/dev/null 2>&1 || { echo "❌ $1 required but not found"; exit 1; }
}

check_prereq git
check_prereq gh
check_prereq python3

cd "$REPO_ROOT"

echo "═══ Phase 4 — Push & PR ═══"
echo ""

# ── Step 1: Verify we're on the right branch ────────

CURRENT=$(git branch --show-current)
if [ "$CURRENT" != "$BRANCH" ]; then
  echo "⚠️  Not on $BRANCH (on $CURRENT). Switching..."
  git checkout "$BRANCH"
fi

# ── Step 2: Run tests locally ────────────────────────

echo "Step 1: Running tests..."
python3 -m pytest -q 2>&1 | tail -3
echo ""

echo "Step 2: Checking lint..."
python3 -m ruff check src/ tests/ --quiet && echo "  ✓ Lint clean" || echo "  ✗ Lint issues found"
python3 -m ruff format --check src/ tests/ --quiet && echo "  ✓ Format clean" || echo "  ✗ Format issues found"
echo ""

# ── Step 3: Verify CLI works ─────────────────────────

echo "Step 3: Verifying CLI..."
TMPWS=$(mktemp -d)
python3 -m assistonauts init "$TMPWS" >/dev/null 2>&1
python3 -m assistonauts explore --help >/dev/null 2>&1 && echo "  ✓ explore command registered" || echo "  ✗ explore command missing"
rm -rf "$TMPWS"
echo ""

# ── Step 4: Push branch ──────────────────────────────

echo "Step 4: Pushing branch to origin..."
git push origin "$BRANCH"
echo ""

# ── Step 5: Create PR ────────────────────────────────

echo "Step 5: Creating PR..."
PR_URL=$(gh pr create \
  --base "$BASE_BRANCH" \
  --head "$BRANCH" \
  --title "Phase 4: Explorer + Interactive Mode" \
  --body "$(cat <<'PRBODY'
## Summary

Implements all Phase 4 deliverables — the Explorer agent for query synthesis and an interactive REPL for human-driven Q&A against the knowledge base.

- **Explorer agent** — query flow via multi-pass retrieval, answer synthesis with citations to wiki articles, conversation history for follow-up questions
- **Explorer toolkit** — citation formatter, context budget calculator, output renderers (markdown, Marp slides, matplotlib chart data)
- **Exploration filing** — save answers to `wiki/explorations/` with YAML frontmatter, all 5 schema sections (Question, Analysis, Findings, Open Questions, Sources)
- **Interactive REPL** — Click-based CLI with `/quit`, `/save`, `/help` commands, conversational flow across questions, Rich markdown output
- **Contract tests** — 14 structural validation tests with recorded LLM fixtures in `tests/fixtures/explorer/`
- **CLI** — `assistonauts explore` with `--query` single-shot mode, `--save` flag, and interactive REPL default
- **Prerequisite** — Gemini Embedding 2 integration via litellm (from prior session)

## Test plan

- 488 tests passing, 0 failing (up from 421 baseline)
- 67 new tests: 29 toolkit, 9 agent, 9 filing, 6 CLI, 14 contract
- `pytest && ruff check src/ tests/ && ruff format --check src/ tests/`
- Manual: `assistonauts explore --help` shows all options
- Manual: `assistonauts explore -w /path/to/kb --query "question"` answers a query

🤖 Generated with [Claude Code](https://claude.com/claude-code)
PRBODY
)" 2>&1)

echo "  PR: $PR_URL"
echo ""

# ── Verification ─────────────────────────────────────
echo "═══ Verification ═══"

PASS=0; FAIL=0

verify() {
  if eval "$1" >/dev/null 2>&1; then
    echo "  ✓ $2"; ((PASS++))
  else
    echo "  ✗ $2"; ((FAIL++))
  fi
}

verify "git log origin/$BRANCH --oneline -1" \
  "Branch pushed to origin"

verify "gh pr view --json state -q '.state' | grep -q OPEN" \
  "PR exists and is open"

verify "python3 -m pytest -q 2>&1 | tail -1 | grep -q passed" \
  "Tests pass locally"

echo ""
echo "Results: $PASS passed, $FAIL failed"

# ── Report ───────────────────────────────────────────
if [ "$FAIL" -eq 0 ]; then
  echo ""
  echo "All checks passed."
  echo "Review the PR, then merge when satisfied."
  echo "After merge, Phase 5 (Captain + Expedition Orchestration) is unblocked."
else
  echo ""
  echo "Some checks failed. Review output above before merging."
fi
