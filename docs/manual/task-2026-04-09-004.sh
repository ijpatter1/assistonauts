#!/bin/bash
# ═══════════════════════════════════════════════════════
# E2E Pipeline Test — "There's Treasure Inside" (105 images)
# Created: 2026-04-09, session-2026-04-09-003
# Phase: 4
# Blocks: nothing (validation only)
#
# Full pipeline test: ingest 105 book page screenshots via
# Scout (vision), compile into wiki articles, index with
# Archivist, cross-reference with Curator, and query with
# the new Explorer. Validates every phase (1-4) works
# end-to-end with real LLM calls against real content.
#
# Requires: ANTHROPIC_API_KEY, GEMINI_API_KEY
# Expected duration: 20-40 minutes (LLM-bound)
#
# Usage: bash docs/manual/task-2026-04-09-004.sh
# ═══════════════════════════════════════════════════════
set -euo pipefail

# ── User Configuration ───────────────────────────────

INPUT_DIR="${INPUT_DIR:-input_artifacts}"
WORKSPACE="${WORKSPACE:-test-kb}"
BATCH_SIZE="${BATCH_SIZE:-10}"  # images per scout ingest call

# ── Prerequisites ────────────────────────────────────

echo "═══ E2E Pipeline Test — There's Treasure Inside ═══"
echo ""

check_prereq() {
  command -v "$1" >/dev/null 2>&1 || { echo "❌ $1 required but not found"; exit 1; }
}

check_prereq python3
check_prereq assistonauts

[ -n "${ANTHROPIC_API_KEY:-}" ] || { echo "❌ ANTHROPIC_API_KEY not set"; exit 1; }
[ -n "${GEMINI_API_KEY:-}" ]    || { echo "❌ GEMINI_API_KEY not set"; exit 1; }

IMAGE_COUNT=$(ls "$INPUT_DIR"/*.png 2>/dev/null | wc -l)
[ "$IMAGE_COUNT" -gt 0 ] || { echo "❌ No .png files found in $INPUT_DIR"; exit 1; }

echo "Input: $IMAGE_COUNT images from $INPUT_DIR"
echo "Workspace: $WORKSPACE"
echo "Batch size: $BATCH_SIZE"
echo ""

SECONDS=0  # bash builtin timer

# ── Stage 1: Initialize Workspace ────────────────────

echo "━━━ Stage 1: Init Workspace ━━━"
if [ -d "$WORKSPACE/.assistonauts" ]; then
  echo "  Existing workspace found at $WORKSPACE — reusing it."
  echo "  (Set WORKSPACE to a new path or delete manually to start fresh.)"
else
  assistonauts init "$WORKSPACE"
  echo "  ✓ Workspace created at $WORKSPACE"
fi
echo ""

# ── Stage 2: Ingest Images via Scout ─────────────────

echo "━━━ Stage 2: Scout Ingest ($IMAGE_COUNT images) ━━━"
echo "  This is the longest stage — each image needs vision LLM processing."
echo ""

INGESTED=0
FAILED=0
BATCH=()

for img in $(ls "$INPUT_DIR"/*.png | sort); do
  BATCH+=("$img")

  if [ "${#BATCH[@]}" -ge "$BATCH_SIZE" ]; then
    echo "  Ingesting batch ($INGESTED+${#BATCH[@]}/$IMAGE_COUNT)..."
    if assistonauts scout ingest "${BATCH[@]}" -w "$WORKSPACE" 2>&1 | tail -"$BATCH_SIZE"; then
      INGESTED=$((INGESTED + ${#BATCH[@]}))
    else
      echo "  ⚠️  Batch had errors (continuing)"
      FAILED=$((FAILED + ${#BATCH[@]}))
    fi
    BATCH=()
  fi
done

# Remaining batch
if [ "${#BATCH[@]}" -gt 0 ]; then
  echo "  Ingesting final batch ($INGESTED+${#BATCH[@]}/$IMAGE_COUNT)..."
  if assistonauts scout ingest "${BATCH[@]}" -w "$WORKSPACE" 2>&1 | tail -"${#BATCH[@]}"; then
    INGESTED=$((INGESTED + ${#BATCH[@]}))
  else
    FAILED=$((FAILED + ${#BATCH[@]}))
  fi
fi

RAW_COUNT=$(ls "$WORKSPACE"/raw/articles/*.md 2>/dev/null | wc -l)
echo ""
echo "  Ingested: $INGESTED, Failed: $FAILED, Raw articles: $RAW_COUNT"
STAGE2_TIME=$SECONDS
echo "  Time: ${STAGE2_TIME}s"
echo ""

if [ "$RAW_COUNT" -lt 5 ]; then
  echo "❌ Too few articles ingested ($RAW_COUNT). Check LLM config."
  exit 1
fi

# ── Stage 3: Plan + Compile ──────────────────────────

echo "━━━ Stage 3: Plan + Compile ━━━"
echo "  Compiler will analyze raw sources and produce wiki articles."
echo ""

assistonauts plan --execute -w "$WORKSPACE" 2>&1 | tail -20

WIKI_COUNT=$(find "$WORKSPACE/wiki" -name "*.md" -not -path "*/explorations/*" 2>/dev/null | wc -l)
SUMMARY_COUNT=$(find "$WORKSPACE/wiki" -name "*.summary.json" 2>/dev/null | wc -l)
echo ""
echo "  Wiki articles: $WIKI_COUNT"
echo "  Summaries: $SUMMARY_COUNT"
STAGE3_TIME=$((SECONDS - STAGE2_TIME))
echo "  Time: ${STAGE3_TIME}s"
echo ""

if [ "$WIKI_COUNT" -lt 1 ]; then
  echo "❌ No wiki articles compiled. Check Compiler output above."
  exit 1
fi

# ── Stage 4: Index with Archivist ────────────────────

echo "━━━ Stage 4: Index (FTS + Embeddings) ━━━"

assistonauts index -w "$WORKSPACE" 2>&1 | tail -10

STAGE4_TIME=$((SECONDS - STAGE2_TIME - STAGE3_TIME))
echo "  Time: ${STAGE4_TIME}s"
echo ""

# ── Stage 5: Curate Cross-References ─────────────────

echo "━━━ Stage 5: Curate ━━━"

assistonauts curate -w "$WORKSPACE" 2>&1 | tail -5

echo ""
echo "  Structural proposals:"
assistonauts curate --proposals -w "$WORKSPACE" 2>&1 | tail -10

STAGE5_TIME=$((SECONDS - STAGE2_TIME - STAGE3_TIME - STAGE4_TIME))
echo ""
echo "  Time: ${STAGE5_TIME}s"
echo ""

# ── Stage 6: Explorer Queries ────────────────────────

echo "━━━ Stage 6: Explorer Queries ━━━"
echo ""

QUERIES=(
  "What is the book 'There's Treasure Inside' about?"
  "What gemstones or minerals are featured in the treasure?"
  "Who is Jon Collins-Black and what motivated him to create this treasure hunt?"
  "What advice does the book give about preparation and planning?"
  "How many treasure boxes are hidden and where are they located?"
)

QUERY_PASS=0
QUERY_FAIL=0

for q in "${QUERIES[@]}"; do
  echo "  Q: $q"
  OUTPUT=$(assistonauts explore -w "$WORKSPACE" --query "$q" 2>&1)
  if [ $? -eq 0 ] && [ -n "$OUTPUT" ]; then
    # Show first 3 lines of answer
    echo "$OUTPUT" | head -5 | sed 's/^/     /'
    echo "     ..."
    ((QUERY_PASS++))
  else
    echo "     ❌ Query failed"
    ((QUERY_FAIL++))
  fi
  echo ""
done

echo "  Queries: $QUERY_PASS passed, $QUERY_FAIL failed"

# ── Stage 7: File an Exploration ─────────────────────

echo ""
echo "━━━ Stage 7: File Exploration ━━━"

assistonauts explore -w "$WORKSPACE" \
  --query "Summarize the key themes and treasures described in the book" \
  --save 2>&1 | tail -5

EXPLORATION_COUNT=$(find "$WORKSPACE/wiki/explorations" -name "*.md" 2>/dev/null | wc -l)
echo "  Filed explorations: $EXPLORATION_COUNT"
echo ""

# ── Stage 8: Status Overview ─────────────────────────

echo "━━━ Stage 8: Final Status ━━━"
echo ""
assistonauts status -w "$WORKSPACE"

TOTAL_TIME=$SECONDS
echo ""

# ── Verification ─────────────────────────────────────
echo ""
echo "═══ Verification ═══"

PASS=0; FAIL=0

verify() {
  if eval "$1" >/dev/null 2>&1; then
    echo "  ✓ $2"; ((PASS++))
  else
    echo "  ✗ $2"; ((FAIL++))
  fi
}

verify "test -d '$WORKSPACE/.assistonauts'" \
  "Workspace initialized"

verify "test $(ls '$WORKSPACE'/raw/articles/*.md 2>/dev/null | wc -l) -ge 10" \
  "At least 10 raw articles ingested"

verify "test $(find '$WORKSPACE/wiki' -name '*.md' -not -path '*/explorations/*' 2>/dev/null | wc -l) -ge 1" \
  "At least 1 wiki article compiled"

verify "test -f '$WORKSPACE/index/assistonauts.db'" \
  "Archivist database exists"

verify "test $QUERY_PASS -ge 3" \
  "At least 3 Explorer queries succeeded"

verify "test $(find '$WORKSPACE/wiki/explorations' -name '*.md' 2>/dev/null | wc -l) -ge 1" \
  "At least 1 exploration filed"

echo ""
echo "Results: $PASS passed, $FAIL failed"
echo ""

# ── Summary ──────────────────────────────────────────
echo "═══ Pipeline Summary ═══"
echo ""
echo "  Input images:      $IMAGE_COUNT"
echo "  Raw articles:      $RAW_COUNT"
echo "  Wiki articles:     $WIKI_COUNT"
echo "  Summaries:         $SUMMARY_COUNT"
echo "  Explorer queries:  $QUERY_PASS/$((QUERY_PASS + QUERY_FAIL)) passed"
echo "  Explorations:      $EXPLORATION_COUNT"
echo "  Total time:        $((TOTAL_TIME / 60))m $((TOTAL_TIME % 60))s"
echo ""
echo "  Stage breakdown:"
echo "    Scout ingest:    ${STAGE2_TIME}s"
echo "    Compile:         ${STAGE3_TIME}s"
echo "    Index:           ${STAGE4_TIME}s"
echo "    Curate:          ${STAGE5_TIME}s"
echo ""

if [ "$FAIL" -eq 0 ]; then
  echo "All checks passed. Full pipeline validated end-to-end."
  echo "Workspace preserved at: $WORKSPACE"
else
  echo "Some checks failed. Review output above."
  echo "Workspace preserved at: $WORKSPACE for inspection."
fi
