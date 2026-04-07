#!/bin/bash
# .claude/hooks/stop-check.sh
# Stop hook — checks if there are uncommitted changes or if handoff hasn't been done.
# This is advisory, not blocking — it adds context for Claude.
#
# IMPORTANT: Check stop_hook_active to prevent infinite loops.
# When a Stop hook returns exit 2, Claude continues working,
# which re-triggers the Stop hook. The stop_hook_active field
# is true on subsequent invocations.

INPUT=$(cat)

# Always allow stopping on subsequent invocations to prevent loops
if [ "$(echo "$INPUT" | jq -r '.stop_hook_active')" = "true" ]; then
  exit 0
fi

REMINDERS=""

# Check 1: Uncommitted changes (definitive signal that work isn't wrapped up)
if [ -d ".git" ]; then
  UNCOMMITTED=$(git status --porcelain 2>/dev/null)
  if [ -n "$UNCOMMITTED" ]; then
    NUM_FILES=$(echo "$UNCOMMITTED" | wc -l | tr -d ' ')
    REMINDERS="There are $NUM_FILES uncommitted file(s). "
  fi
fi

# Check 2: No handoff artifact from today (suggests /handoff wasn't run)
if [ -d "docs/sessions" ]; then
  TODAY=$(date +%Y-%m-%d)
  TODAY_HANDOFFS=$(ls docs/sessions/session-${TODAY}-*.md 2>/dev/null | wc -l | tr -d ' ')
  if [ "$TODAY_HANDOFFS" = "0" ]; then
    REMINDERS="${REMINDERS}No session handoff artifact exists for today. "
  fi
fi

if [ -n "$REMINDERS" ]; then
  jq -n --arg r "${REMINDERS}Before ending, consider: (1) Commit any outstanding work. (2) Run /evaluate for a QA assessment. (3) Run /handoff to generate a session artifact. If you are intentionally ending without these, that is fine — this is a reminder, not a requirement." '{
    decision: "approve",
    reason: "Advisory reminder — not blocking",
    systemMessage: $r
  }'
fi

exit 0