#!/bin/bash
# ═══════════════════════════════════════════════════════
# Push Phase 3 Branch and Create PR
# Created: 2026-04-08, session-2026-04-08-005
# Phase: 3
# Blocks: Phase 4 start (Explorer + Interactive Mode)
#
# Phase 2+3 work is complete on phase/3-archivist-curator-rag
# (36 commits, 378 tests). This script pushes the branch
# to GitHub and creates the PR for merge into main.
#
# Usage: bash docs/manual/task-2026-04-08-001.sh
# ═══════════════════════════════════════════════════════
set -euo pipefail

# ── Prerequisites ────────────────────────────────────

check_prereq() {
  command -v "$1" >/dev/null 2>&1 || { echo "❌ $1 required but not found"; exit 1; }
}

check_prereq git
check_prereq gh
check_prereq python3

echo "Checking we're on the right branch..."
BRANCH=$(git branch --show-current)
if [ "$BRANCH" != "phase/3-archivist-curator-rag" ]; then
  echo "❌ Expected branch phase/3-archivist-curator-rag, got $BRANCH"
  exit 1
fi
echo "  ✓ On branch $BRANCH"

# ── Step 1: Run tests ───────────────────────────────

echo ""
echo "Step 1: Running tests..."
python3 -m pytest -q
echo "  ✓ Tests passed"

echo ""
echo "Step 2: Checking lint..."
python3 -m ruff check src/ tests/
python3 -m ruff format --check src/ tests/
echo "  ✓ Lint clean"

# ── Step 3: Push branch ─────────────────────────────

echo ""
echo "Step 3: Pushing branch to origin..."
git push origin phase/3-archivist-curator-rag
echo "  ✓ Branch pushed"

# ── Step 4: Create PR ───────────────────────────────

echo ""
echo "Step 4: Creating pull request..."

PR_URL=$(gh pr create \
  --base main \
  --head phase/3-archivist-curator-rag \
  --title "Phase 2+3: Task Runner, Compiler Plan Mode, Archivist, Curator, Hybrid RAG" \
  --body "$(cat <<'PREOF'
## Summary

Completes Phase 2 (12 deliverables) and Phase 3 (19 deliverables):

**Phase 2 additions:**
- Multi-source compilation (`compile_multi()`, `--source` repeatable)
- Compiler plan mode (`compiler.plan()` — editorial triage for article types/groupings)
- Task/Mission vocabulary refactor (MissionRunner → TaskRunner throughout)

**Phase 3:**
- Archivist system (deterministic KB OS, SQLite + FTS5 + sqlite-vec)
- Embedding generation with chunking, batching, auto-resize for large images
- Hybrid retrieval with Reciprocal Rank Fusion
- 4-pass multi-pass retrieval with short-circuit mode
- Curator agent (singleton, cross-referencing, structural proposals)
- LLM response cache (SQLite, SHA-256 keyed, TTL, eviction)
- Image ingestion via vision models (Haiku 4.5, multimodal content blocks)
- Batch ingestion (`scout ingest` accepts multiple files)
- CLI: `status`, `index`, `curate`, `plan`

## Test plan
- 378 tests passing, 0 failing
- `pytest && ruff check src/ tests/ && ruff format --check src/ tests/`
- Manual: `assistonauts plan -w /tmp/test-kb` shows compilation plan
- Manual: `assistonauts scout ingest a.png b.png -w /tmp/test-kb`

🤖 Generated with [Claude Code](https://claude.com/claude-code)
PREOF
)")

echo "  ✓ PR created: $PR_URL"

# ── Verification ─────────────────────────────────────
echo ""
echo "═══ Verification ═══"

PASS=0; FAIL=0

verify() {
  if eval "$1"; then
    echo "  ✓ $2"; ((PASS++))
  else
    echo "  ✗ $2"; ((FAIL++))
  fi
}

verify 'git log origin/phase/3-archivist-curator-rag --oneline -1 >/dev/null 2>&1' \
  "Branch exists on remote"

verify 'gh pr list --head phase/3-archivist-curator-rag --json number --jq "length" | grep -q "[1-9]"' \
  "PR exists"

verify 'python3 -m pytest -q 2>&1 | tail -1 | grep -q "passed"' \
  "Tests pass"

echo ""
echo "Results: $PASS passed, $FAIL failed"

if [ "$FAIL" -eq 0 ]; then
  echo ""
  echo "All checks passed. Review and merge the PR."
else
  echo ""
  echo "Some checks failed. Review output above."
fi
