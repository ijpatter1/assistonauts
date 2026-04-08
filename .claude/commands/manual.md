Generate an actionable artifact for work that must be performed outside the sandbox.

Use this when you've done everything possible inside the sandbox but the remaining step requires human action — deploying, configuring a third-party UI, testing on a real device, running commands that need network access beyond the firewall, etc.

## Core Principle: Maximize Automation, Minimize Human Effort

**Your job is to minimize the human's work, not to describe work for them to do.** Before writing anything, ask yourself: can I produce an artifact that the human runs rather than reads?

**Prefer this hierarchy:**

1. **Executable script** — a bash script the human runs with `bash docs/manual/task-NNN.sh`. Includes prerequisite checks, the actual commands, verification assertions, and a summary. The human runs one command and reviews the results.
2. **Makefile target** — if the task is recurring or belongs in the project workflow, add a Makefile target. `make deploy` is better than "run these 8 commands."
3. **Minimal task card with companion script** — if the task genuinely requires interactive steps (clicking through a UI, visual inspection), write a short card for the manual parts and a script for everything else. The card says "Run `bash docs/manual/task-NNN.sh`, then do [one UI step], then run `bash docs/manual/task-NNN-verify.sh`."
4. **Prose task card** — last resort, only for tasks that are entirely non-scriptable (design review, stakeholder demo, content approval).

**Anti-patterns to avoid:**

- A 20-step numbered list where each step is a command to copy-paste. That's a script with comments. Write the script.
- "Expected result: you should see X" after a command. That's an assertion. Write `if [check]; then echo "✓ passed"; else echo "✗ FAILED"; fi`.
- Configuration blocks the human copies into a file. That's a heredoc in a script, or a file you create directly.
- "Verify by running..." at the end. Build verification into the script as a final step.

## What to Generate

$ARGUMENTS

If no arguments are provided, describe what you just completed and what manual step remains.

## Output Location

Create files at `docs/manual/` (create the directory if it doesn't exist). Naming convention:

- Scripts: `task-YYYY-MM-DD-NNN.sh` (or `.py` if Python fits better)
- Task cards (for non-scriptable work only): `task-YYYY-MM-DD-NNN.md`
- Supporting files: `task-YYYY-MM-DD-NNN-config.yaml`, etc.

Where NNN is a zero-padded sequence number for the day.

## Script Template

When the task is scriptable (the default — see Decision Guide below), produce this:

```bash
#!/bin/bash
# ═══════════════════════════════════════════════════════
# [Short Title]
# Created: YYYY-MM-DD, session-YYYY-MM-DD-NNN
# Phase: N
# Blocks: [what downstream work is blocked, or "nothing"]
#
# [2-3 sentences: what the agent built and what this
# script completes. Not a novel — just enough context
# so the human knows what they're running and why.]
#
# Usage: bash docs/manual/task-YYYY-MM-DD-NNN.sh
# ═══════════════════════════════════════════════════════
set -euo pipefail

# ── User Configuration ───────────────────────────────
# Variables the human might need to change. All at the
# top, never scattered through the script.

PROJECT_ID="${GCP_PROJECT:-your-project-id}"  # ← change if not in env

# ── Prerequisites ────────────────────────────────────
# Fail fast with clear messages if something's missing.

check_prereq() {
  command -v "$1" >/dev/null 2>&1 || { echo "❌ $1 required but not found"; exit 1; }
}

check_prereq gcloud
check_prereq curl
[ -n "${ANTHROPIC_API_KEY:-}" ] || { echo "❌ ANTHROPIC_API_KEY not set"; exit 1; }

# ── Execution ────────────────────────────────────────

echo "Step 1: Doing the thing..."
# actual commands here

echo "Step 2: Doing the next thing..."
# actual commands here

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

verify 'curl -s -o /dev/null -w "%{http_code}" https://example.com | grep -q 200' \
  "Endpoint returns 200"

verify 'test -f /tmp/output/result.json' \
  "Output file created"

echo ""
echo "Results: $PASS passed, $FAIL failed"

# ── Report ───────────────────────────────────────────
if [ "$FAIL" -eq 0 ]; then
  echo ""
  echo "All checks passed. Update task status to 'done'."
else
  echo ""
  echo "Some checks failed. Review output above."
  echo "Set task status to 'blocked' with notes on what failed."
fi
```

## Task Card Template

Use this for tasks that genuinely cannot be scripted — navigating a third-party UI that has no API, visual design review, physical device testing. If any part of the task IS scriptable, extract it into a companion script and reference it from the card.

```markdown
# Manual Task — [Short Title]

**Created:** YYYY-MM-DD, session-YYYY-MM-DD-NNN
**Phase:** N
**Status:** pending
**Priority:** [high | medium | low]
**Blocks:** [what downstream work is blocked until this is done, or "nothing"]

## Context

[What the agent did inside the sandbox that led to this task. Include specific files created or modified, commits, and the current state. 2-3 sentences — the human should understand where things stand without reading the full session history.]

## Steps

[Only the parts that require human judgment or interaction. Reference companion scripts for automatable parts.]

1. Run `bash docs/manual/task-NNN-setup.sh` (if applicable)
2. [Manual step with exact UI navigation path or specific action]
   - Expected result: [what they should see]
3. Run `bash docs/manual/task-NNN-verify.sh` (if applicable)

## Report Back

When complete, update the **Status** field above to `done` and add:

**Completed:** YYYY-MM-DD
**Notes:** [any observations, unexpected outcomes, or configuration values the agent needs to know]

If something didn't work as expected, set Status to `blocked` and describe what happened in Notes. The agent will read this on the next session start.
```

### Task Card Rules

When writing task cards (not scripts), follow these rules for the Steps section:

- Be extremely specific. "Deploy to Vercel" is bad. "Run `vercel --prod` from the project root, or push to the `main` branch which triggers auto-deployment via the GitHub integration" is good.
- Include any credentials, IDs, or configuration values the human will need. If sensitive, reference where to find them rather than writing them inline.
- For third-party UIs, include the exact navigation path: "Go to tagmanager.google.com → Account 6346433751 → Container → Tags → New"
- State what's blocked. If nothing downstream depends on this, say so — it helps the human prioritize.
- Verification checks should be runnable, not visual. Prefer `curl` commands, URL checks, or specific log entries over "confirm it looks right."

## Decision Guide

Before choosing a format, ask:

1. **Is every step a command?** → Script. Period.
2. **Are most steps commands but one step needs a UI?** → Script for the commands + short task card for the UI step.
3. **Is the task entirely visual/interactive?** → Short task card.
4. **Will this task recur?** → Makefile target, not a one-off script.

## After Creating the Artifact

1. Make scripts executable: `chmod +x docs/manual/task-*.sh`
2. Note the task in the handoff artifact under **Blocked** or **In Progress** with a reference to the task file
3. If the task blocks a phase deliverable, mark it as ❌ in PHASE_STATUS.md with a reference to the task card
4. Continue working on other deliverables that aren't blocked by this task
5. Tell the user: "Created `docs/manual/task-YYYY-MM-DD-NNN.sh` — run it when you're ready"