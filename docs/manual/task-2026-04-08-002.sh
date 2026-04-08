#!/bin/bash
# ═══════════════════════════════════════════════════════
# End-to-End Pipeline Test: "There's Treasure Inside"
# Created: 2026-04-08, session-2026-04-08-005
# Phase: 3
# Blocks: Nothing — validation task for Phase 4 readiness
#
# Tests the full build pipeline with real book screenshots:
# init → scout ingest (vision) → plan → compile → index →
# curate → status. Uses Claude Haiku 4.5 for LLM calls.
#
# Usage: bash docs/manual/task-2026-04-08-002.sh
# ═══════════════════════════════════════════════════════
set -euo pipefail

# ── User Configuration ───────────────────────────────

# Resolve paths relative to the project root
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

INPUT_DIR="${INPUT_DIR:-$PROJECT_ROOT/input_artifacts}"
WORKSPACE="$PROJECT_ROOT/test-kb"

# ── Prerequisites ────────────────────────────────────

check_prereq() {
  command -v "$1" >/dev/null 2>&1 || { echo "❌ $1 required but not found"; exit 1; }
}

check_prereq assistonauts
check_prereq python3
[ -n "${ANTHROPIC_API_KEY:-}" ] || { echo "❌ ANTHROPIC_API_KEY not set"; exit 1; }

# Check input files exist
EXPECTED_FILES=(
  "cover.png"
  "front-01-02.png"
  "front-03-04.png"
  "page-008-009.png"
  "page-010-011.png"
  "page-012-013.png"
  "page-014-015.png"
  "page-016-017.png"
)

echo "Checking input files in $INPUT_DIR..."
for f in "${EXPECTED_FILES[@]}"; do
  if [ ! -f "$INPUT_DIR/$f" ]; then
    echo "❌ Missing: $INPUT_DIR/$f"
    exit 1
  fi
done
echo "  ✓ All 8 input files found"

# ── Step 1: Initialize workspace ─────────────────────

echo ""
echo "Step 1: Initializing workspace at $WORKSPACE..."
rm -rf "$WORKSPACE"
assistonauts init "$WORKSPACE"
echo "  ✓ Workspace created"

# ── Step 2: Batch ingest all page screenshots ────────

echo ""
echo "Step 2: Ingesting 8 page screenshots (using Haiku vision)..."
echo "  This will make 8 API calls — may take a minute..."

assistonauts scout ingest \
  "$INPUT_DIR/cover.png" \
  "$INPUT_DIR/front-01-02.png" \
  "$INPUT_DIR/front-03-04.png" \
  "$INPUT_DIR/page-008-009.png" \
  "$INPUT_DIR/page-010-011.png" \
  "$INPUT_DIR/page-012-013.png" \
  "$INPUT_DIR/page-014-015.png" \
  "$INPUT_DIR/page-016-017.png" \
  -w "$WORKSPACE"

echo "  ✓ Ingestion complete"

# ── Step 3: Check transcription quality ──────────────

echo ""
echo "Step 3: Checking transcription quality..."
echo "  --- First 10 lines of page-008-009.md (Introduction) ---"
head -15 "$WORKSPACE/raw/articles/page-008-009.md"
echo "  ---"
echo ""
echo "  ⚠️  Review: does the transcription look reasonable?"
echo "     If garbled, check ANTHROPIC_API_KEY and model config."

# ── Step 4: Run Compiler plan mode ───────────────────

echo ""
echo "Step 4: Running Compiler plan mode..."
echo "  Analyzing sources and proposing compilation plan..."
assistonauts plan -w "$WORKSPACE"

echo ""
echo "  ⚠️  Review the plan above. Does it make sense?"
read -p "  Press Enter to execute the plan, or Ctrl+C to abort..."

# ── Step 5: Execute the plan ─────────────────────────

echo ""
echo "Step 5: Executing compilation plan..."
assistonauts plan --execute -w "$WORKSPACE"
echo "  ✓ Compilation complete"

# ── Step 6: Index all articles ───────────────────────

echo ""
echo "Step 6: Indexing articles..."
assistonauts index -w "$WORKSPACE"
echo "  ✓ Indexing complete"

# ── Step 7: Structural analysis ──────────────────────

echo ""
echo "Step 7: Running structural analysis..."
assistonauts curate --proposals -w "$WORKSPACE"

# ── Step 8: Status overview ──────────────────────────

echo ""
echo "Step 8: Knowledge base status..."
assistonauts status -w "$WORKSPACE"

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

verify 'test $(ls "$WORKSPACE/raw/articles/"*.md 2>/dev/null | wc -l) -eq 8' \
  "8 raw sources ingested"

verify 'test $(find "$WORKSPACE/raw/articles/" -name "*.md" -size +100c | wc -l) -ge 6' \
  "At least 6 transcriptions are non-trivial (>100 bytes)"

WIKI_COUNT=$(find "$WORKSPACE/wiki/" -name "*.md" 2>/dev/null | wc -l)
verify 'test "$WIKI_COUNT" -ge 1' \
  "At least 1 wiki article compiled ($WIKI_COUNT found)"

SUMMARY_COUNT=$(find "$WORKSPACE/wiki/" -name "*.summary.json" 2>/dev/null | wc -l)
verify 'test "$SUMMARY_COUNT" -ge 1' \
  "At least 1 content summary generated ($SUMMARY_COUNT found)"

verify 'test -f "$WORKSPACE/index/assistonauts.db"' \
  "Archivist database exists"

DB_ARTICLES=$(python3 -c "
import sqlite3
db = sqlite3.connect('$WORKSPACE/index/assistonauts.db')
print(db.execute('SELECT count(*) FROM articles').fetchone()[0])
" 2>/dev/null || echo "0")
verify 'test "$DB_ARTICLES" -ge 1' \
  "At least 1 article indexed in DB ($DB_ARTICLES found)"

verify 'test -f "$WORKSPACE/index/manifest.json"' \
  "Manifest file exists"

echo ""
echo "Results: $PASS passed, $FAIL failed"

if [ "$FAIL" -eq 0 ]; then
  echo ""
  echo "═══ Pipeline test PASSED ═══"
  echo ""
  echo "Workspace at: $WORKSPACE"
  echo "Wiki articles: $(find "$WORKSPACE/wiki/" -name "*.md" | head -10)"
else
  echo ""
  echo "═══ Some checks failed ═══"
  echo "Review the output above for details."
fi
