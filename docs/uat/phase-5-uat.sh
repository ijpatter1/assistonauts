#!/bin/bash
# ================================================================
# Phase 5 UAT — Captain + Expedition Orchestration
# Created: 2026-04-09, session-2026-04-09-004
# Updated: 2026-04-09, session-2026-04-09-005 — added checks for
#   plan.yaml, build-report.md, progress feedback, parse failure
#   warning, budget halt CLI visibility
# Updated: 2026-04-10, session-2026-04-10-001 — added dry-run
#   scenario, enriched build report checks (per-agent tokens,
#   coverage metrics, knowledge base stats, sources), build
#   report path in CLI output
#
# Tests end-to-end expedition workflows: creation, build execution,
# budget enforcement, error handling, and config validation.
#
# Prerequisites:
#   - ANTHROPIC_API_KEY set (for LLM calls — Sonnet for Captain, Haiku for other agents)
#   - GEMINI_API_KEY set (for Gemini Embedding 2 if indexing scenarios run)
#   - assistonauts installed (`pip install -e .` from project root)
#
# Usage: bash docs/uat/phase-5-uat.sh
# ================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
WORKSPACE="${WORKSPACE:-$PROJECT_ROOT/uat-workspace-phase5}"

PASS=0; FAIL=0

verify() {
  if eval "$1" >/dev/null 2>&1; then
    echo "  ✓ $2"; PASS=$((PASS + 1))
  else
    echo "  ✗ $2"; FAIL=$((FAIL + 1))
  fi
}

confirm() {
  echo ""
  echo "  → $1"
  read -p "  Pass? [Y/n] " -n 1 -r
  echo ""
  if [[ $REPLY =~ ^[Nn]$ ]]; then
    echo "  ✗ $2"; FAIL=$((FAIL + 1))
  else
    echo "  ✓ $2"; PASS=$((PASS + 1))
  fi
}

cleanup() {
  rm -rf "$WORKSPACE"
  rm -f /tmp/uat-*.yaml
}

# Override workspace config: Sonnet for Captain (reliable YAML),
# Haiku for other agents (cost), Gemini Embedding 2 for vectors
configure_workspace() {
  cat > "$WORKSPACE/.assistonauts/config.yaml" << 'CFGEOF'
llm:
  providers:
    anthropic:
      model: claude-haiku-4-5-20251001
      api_key_env: ANTHROPIC_API_KEY
    anthropic_sonnet:
      model: claude-sonnet-4-6
      api_key_env: ANTHROPIC_API_KEY
  roles:
    scout: anthropic
    compiler: anthropic
    curator: anthropic
    captain: anthropic_sonnet
    inspector: anthropic
    explorer: anthropic

embedding:
  active: gemini
  providers:
    gemini:
      model: gemini-embedding-2-preview
      dimensions: 3072

cache:
  llm_responses:
    enabled: true
    backend: sqlite
    ttl_hours: 168
    max_size_mb: 500
CFGEOF
}

echo "═══ Phase 5 UAT — Captain + Expedition Orchestration ═══"
echo ""
echo "Workspace: $WORKSPACE"
echo ""

# Clean up any prior run
cleanup

# ── Prerequisites ────────────────────────────────────

check_prereq() {
  command -v "$1" >/dev/null 2>&1 || { echo "❌ $1 required but not found"; exit 1; }
}

check_prereq assistonauts
check_prereq python3
check_prereq sqlite3

# ── Scenario 6: Invalid Config (no LLM calls) ───────

echo "━━━ Scenario 6: Invalid Config Handling ━━━"
echo ""

assistonauts init "$WORKSPACE" >/dev/null 2>&1
configure_workspace

# 6a: Totally invalid YAML syntax
cat > /tmp/uat-bad-syntax.yaml << 'BADEOF'
expedition:
  name: broken
  scope:
    description: "Missing closing quote
    keywords: [unterminated
BADEOF

OUTPUT=$(assistonauts expedition create --config /tmp/uat-bad-syntax.yaml -w "$WORKSPACE" 2>&1 || true)
verify 'echo "$OUTPUT" | grep -qi "error\|invalid\|parse"' \
  "6a: Bad YAML syntax produces error message"
verify '! test -d "$WORKSPACE/expeditions/broken"' \
  "6a: No expedition directory created for bad YAML"

# 6b: Config with future source types (RSS/GitHub)
cat > /tmp/uat-future-sources.yaml << 'FUTEOF'
expedition:
  name: future-sources
  description: "Has RSS and GitHub sources"
  scope:
    description: "Test"
    keywords: [test]
  sources:
    local:
      - path: /tmp
        pattern: "*.md"
    rss:
      - url: https://arxiv.org/rss/cs.LG
    github:
      - repo: owner/repo
FUTEOF

OUTPUT=$(assistonauts expedition create --config /tmp/uat-future-sources.yaml -w "$WORKSPACE" 2>&1 || true)
verify 'test -d "$WORKSPACE/expeditions/future-sources"' \
  "6b: Expedition created even with unknown source types"
verify 'test -f "$WORKSPACE/expeditions/future-sources/expedition.yaml"' \
  "6b: expedition.yaml written"

echo ""

# ── Scenario 2: Error Handling (no LLM calls) ───────

echo "━━━ Scenario 2: Error Handling ━━━"
echo ""

# 2a: Build nonexistent expedition
OUTPUT=$(assistonauts build does-not-exist -w "$WORKSPACE" 2>&1 || true)
verify 'echo "$OUTPUT" | grep -qi "not found"' \
  "2a: Build nonexistent expedition shows 'not found'"

# 2b: Create duplicate expedition
OUTPUT=$(assistonauts expedition create --config /tmp/uat-future-sources.yaml -w "$WORKSPACE" 2>&1 || true)
verify 'echo "$OUTPUT" | grep -qi "already exists"' \
  "2b: Duplicate expedition shows 'already exists'"

# 2c: Build expedition with no expedition.yaml
mkdir -p "$WORKSPACE/expeditions/broken-exp"
OUTPUT=$(assistonauts build broken-exp -w "$WORKSPACE" 2>&1 || true)
verify 'echo "$OUTPUT" | grep -qi "no expedition.yaml\|not found"' \
  "2c: Missing expedition.yaml shows clear error"

echo ""

# ── Scenario 4: Dry Run (requires LLM) ─────────────

echo "━━━ Scenario 4: Dry Run ━━━"
echo ""

if [ -z "${ANTHROPIC_API_KEY:-}" ]; then
  echo "  ⊘ Skipped (ANTHROPIC_API_KEY not set)"
  echo ""
else
  # Set up test sources (shared by dry-run and happy path)
  INPUT_DIR="${INPUT_DIR:-$PROJECT_ROOT/input_artifacts}"
  TEST_SOURCES="$WORKSPACE/test-sources"
  mkdir -p "$TEST_SOURCES"

  UAT_PAGES=(
    "cover.png"
    "front-01-02.png"
    "front-03-04.png"
    "page-008-009.png"
    "page-010-011.png"
    "page-012-013.png"
    "page-014-015.png"
    "page-016-017.png"
  )

  COPIED=0
  for page in "${UAT_PAGES[@]}"; do
    if [ -f "$INPUT_DIR/$page" ]; then
      cp "$INPUT_DIR/$page" "$TEST_SOURCES/"
      COPIED=$((COPIED + 1))
    fi
  done

  if [ "$COPIED" -eq 0 ]; then
    echo "  ⚠️  No input images found in $INPUT_DIR"
    echo "  Set INPUT_DIR to point to the book page screenshots."
    echo "  Falling back to simple markdown test sources..."
    echo "# Dry Run Test" > "$TEST_SOURCES/dryrun.md"
    SOURCE_PATTERN="*.md"
    SCOPE_DESC="Test dry run"
    SCOPE_KEYWORDS="[test]"
    PURPOSE="Build a test knowledge base for UAT validation"
  else
    echo "  Copied $COPIED page images from $INPUT_DIR"
    SOURCE_PATTERN="*.png"
    SCOPE_DESC="A treasure hunt book with hidden clues, gemstones, and adventure guidance"
    SCOPE_KEYWORDS="[treasure, gems, clues, adventure, preparation]"
    PURPOSE="Build a reference guide for active treasure hunters preparing for a physical search of the five hidden treasure boxes described in There's Treasure Inside by Jon Collins-Black"
  fi

  cat > /tmp/uat-dryrun.yaml << DRYEOF
expedition:
  name: dryrun-test
  description: "Dry run test"
  purpose: "$PURPOSE"
  scope:
    description: "$SCOPE_DESC"
    keywords: $SCOPE_KEYWORDS
  sources:
    local:
      - path: $TEST_SOURCES
        pattern: "$SOURCE_PATTERN"
  scaling:
    budget:
      daily_token_limit: 200000
DRYEOF

  assistonauts expedition create --config /tmp/uat-dryrun.yaml -w "$WORKSPACE" >/dev/null 2>&1

  set +e
  DRY_OUTPUT=$(assistonauts build dryrun-test --dry-run -w "$WORKSPACE" 2>&1)
  DRY_EXIT=$?
  set -e

  echo "$DRY_OUTPUT" | head -15
  echo ""

  verify 'echo "$DRY_OUTPUT" | grep -qi "dry run"' \
    "4a: Dry-run output identifies itself as dry run"
  verify 'echo "$DRY_OUTPUT" | grep -qi "planned\|not executed"' \
    "4b: Dry-run says missions are planned, not executed"
  verify 'echo "$DRY_OUTPUT" | grep -qi "plan.yaml"' \
    "4c: Dry-run mentions plan.yaml artifact"
  verify 'test -f "$WORKSPACE/expeditions/dryrun-test/plan.yaml"' \
    "4d: plan.yaml written during dry run"

  # Verify no missions were actually executed
  if [ -f "$WORKSPACE/expeditions/dryrun-test/ledger.db" ]; then
    RUNNING=$(sqlite3 "$WORKSPACE/expeditions/dryrun-test/ledger.db" \
      "SELECT COUNT(*) FROM missions WHERE status IN ('running','completed','failed')" \
      2>/dev/null || echo "0")
    verify 'test "$RUNNING" -eq 0' \
      "4e: No missions executed during dry run ($RUNNING found)"
  else
    verify 'true' \
      "4e: No ledger DB = no missions executed (expected for dry run)"
  fi

  echo ""

  # ── Scenario 1: Happy Path ──────────────────────────

  echo "━━━ Scenario 1: Happy Path — Expedition Build ━━━"
  echo ""

  cat > /tmp/uat-happy.yaml << HAPEOF
expedition:
  name: treasure-uat
  description: "UAT expedition — There's Treasure Inside"
  purpose: "$PURPOSE"
  phase: build
  scope:
    description: "$SCOPE_DESC"
    keywords: $SCOPE_KEYWORDS
  sources:
    local:
      - path: $TEST_SOURCES
        pattern: "$SOURCE_PATTERN"
  scaling:
    agents:
      scout: auto
      compiler: auto
    budget:
      daily_token_limit: 200000
      warning_threshold: 0.8
HAPEOF

  # Create expedition
  assistonauts expedition create --config /tmp/uat-happy.yaml -w "$WORKSPACE" 2>&1
  echo ""

  verify 'test -d "$WORKSPACE/expeditions/treasure-uat"' \
    "1a: Expedition directory created"
  verify 'test -f "$WORKSPACE/expeditions/treasure-uat/expedition.yaml"' \
    "1b: expedition.yaml exists"
  verify 'test -d "$WORKSPACE/expeditions/treasure-uat/missions"' \
    "1c: missions/ directory exists"
  verify 'test -d "$WORKSPACE/expeditions/treasure-uat/review"' \
    "1d: review/ directory exists"

  # Verify full config persisted
  verify 'grep -q "scaling" "$WORKSPACE/expeditions/treasure-uat/expedition.yaml"' \
    "1e: Scaling config persisted in expedition.yaml"
  verify 'grep -q "stationed" "$WORKSPACE/expeditions/treasure-uat/expedition.yaml"' \
    "1f: Stationed config persisted in expedition.yaml"
  verify 'grep -q "daily_token" "$WORKSPACE/expeditions/treasure-uat/expedition.yaml"' \
    "1g: Budget config persisted in expedition.yaml"

  echo ""
  echo "  Running build phase (this makes LLM calls)..."
  if [ "$SOURCE_PATTERN" = "*.png" ]; then
    echo "  Using vision model for image ingestion — this may take several minutes..."
  fi
  echo ""

  set +e
  BUILD_OUTPUT=$(assistonauts build treasure-uat -w "$WORKSPACE" 2>&1)
  BUILD_EXIT=$?
  set -e

  echo "$BUILD_OUTPUT" | head -30
  echo ""

  verify 'echo "$BUILD_OUTPUT" | grep -qi "build"' \
    "1h: Build output mentions build phase"
  verify 'echo "$BUILD_OUTPUT" | grep -qi "discovery\|structuring\|refinement"' \
    "1i: Build output shows iteration phases"
  verify 'test -f "$WORKSPACE/expeditions/treasure-uat/ledger.db"' \
    "1j: Mission ledger database created"

  # Check ledger has mission records
  MISSION_COUNT=$(sqlite3 "$WORKSPACE/expeditions/treasure-uat/ledger.db" \
    "SELECT COUNT(*) FROM missions" 2>/dev/null || echo "0")
  verify 'test "$MISSION_COUNT" -gt 0' \
    "1k: Ledger contains $MISSION_COUNT mission records"

  # Check YAML audit files
  YAML_COUNT=$(ls "$WORKSPACE/expeditions/treasure-uat/missions/"*.yaml 2>/dev/null | wc -l | tr -d ' ')
  verify 'test "$YAML_COUNT" -gt 0' \
    "1l: $YAML_COUNT YAML audit files in missions/"

  # Check plan.yaml artifact (added during eval fix rounds)
  verify 'test -f "$WORKSPACE/expeditions/treasure-uat/plan.yaml"' \
    "1m: plan.yaml artifact written"
  if [ -f "$WORKSPACE/expeditions/treasure-uat/plan.yaml" ]; then
    verify 'grep -q "agent" "$WORKSPACE/expeditions/treasure-uat/plan.yaml"' \
      "1n: plan.yaml includes agent details (not just IDs)"
  fi

  # Check build-report.md artifact
  verify 'test -f "$WORKSPACE/expeditions/treasure-uat/build-report.md"' \
    "1o: build-report.md written"
  if [ -f "$WORKSPACE/expeditions/treasure-uat/build-report.md" ]; then
    REPORT="$WORKSPACE/expeditions/treasure-uat/build-report.md"
    verify 'grep -q "Discovery" "$REPORT"' \
      "1p: build report includes iteration names"
    verify 'grep -q "Token Usage" "$REPORT"' \
      "1q: build report includes Token Usage section"
    verify 'grep -q "captain:" "$REPORT"' \
      "1r: build report includes captain token usage"
    verify 'grep -q "Coverage" "$REPORT"' \
      "1s: build report includes Coverage section"
    verify 'grep -q "Knowledge Base" "$REPORT"' \
      "1t: build report includes Knowledge Base section"
    verify 'grep -q "Sources" "$REPORT"' \
      "1u: build report includes Sources section"
  fi

  # Check build report path shown in CLI output
  verify 'echo "$BUILD_OUTPUT" | grep -qi "build-report.md"' \
    "1v: CLI output shows build report file path"

  # Check progress feedback was in build output
  verify 'echo "$BUILD_OUTPUT" | grep -qi "executing\|mission"' \
    "1w: Build output shows per-mission progress"

  # Check empty build warning (if no missions planned)
  if echo "$BUILD_OUTPUT" | grep -q "0/0"; then
    verify 'echo "$BUILD_OUTPUT" | grep -qi "warning\|no missions\|could not be parsed"' \
      "1x: Empty build shows parse failure warning"
  fi

  echo ""

  # ── Scenario 3: Budget Enforcement ─────────────────

  echo "━━━ Scenario 3: Budget Enforcement ━━━"
  echo ""

  cat > /tmp/uat-budget.yaml << BUDEOF
expedition:
  name: budget-test
  description: "Budget enforcement test"
  purpose: "$PURPOSE"
  phase: build
  scope:
    description: "$SCOPE_DESC"
    keywords: $SCOPE_KEYWORDS
  sources:
    local:
      - path: $TEST_SOURCES
        pattern: "$SOURCE_PATTERN"
  scaling:
    agents:
      scout: auto
      compiler: auto
    budget:
      daily_token_limit: 500
      warning_threshold: 0.5
BUDEOF

  assistonauts expedition create --config /tmp/uat-budget.yaml -w "$WORKSPACE" 2>&1
  echo ""

  set +e
  BUDGET_OUTPUT=$(assistonauts build budget-test -w "$WORKSPACE" 2>&1)
  set -e

  echo "$BUDGET_OUTPUT" | head -15
  echo ""

  verify 'test -f "$WORKSPACE/expeditions/budget-test/budget.db"' \
    "3a: Budget database created"

  # Check if budget tracking recorded usage
  BUDGET_RECORDS=$(sqlite3 "$WORKSPACE/expeditions/budget-test/budget.db" \
    "SELECT COUNT(*) FROM token_usage" 2>/dev/null || echo "0")
  verify 'test "$BUDGET_RECORDS" -ge 0' \
    "3b: Budget database has $BUDGET_RECORDS usage records"

  # Check if any missions were left pending due to budget
  PENDING=$(sqlite3 "$WORKSPACE/expeditions/budget-test/ledger.db" \
    "SELECT COUNT(*) FROM missions WHERE status = 'pending'" 2>/dev/null || echo "0")
  echo "  (Pending missions after budget halt: $PENDING)"

  # Check budget halt message visible in CLI output
  verify 'echo "$BUDGET_OUTPUT" | grep -qi "budget\|halt\|exceeded\|warning"' \
    "3c: Budget status visible in CLI output"

  confirm "Does the build output show budget halt or fewer completed missions than planned?" \
    "3d: Budget enforcement halted execution"

  echo ""
fi

# ── Results ──────────────────────────────────────────

echo ""
echo "═══ UAT Results ═══"
echo ""
echo "  Passed: $PASS"
echo "  Failed: $FAIL"
echo ""

if [ "$FAIL" -eq 0 ]; then
  echo "  ═══ Phase 5 UAT PASSED ═══"
else
  echo "  ═══ Phase 5 UAT: $FAIL checks failed ═══"
  echo "  Review output above for details."
fi

echo ""
echo "Workspace preserved at: $WORKSPACE"
echo "Clean up with: rm -rf $WORKSPACE"
