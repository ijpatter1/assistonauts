---
name: evaluate
description: "Run a dual QA review — technical evaluator + product reviewer — on recent work. Use when a feature is complete, before handoff, or when the user wants a quality check on what's been built."
user-invocable: true
---

# Evaluate — Dual QA Review

Run an independent quality assessment of recent work using both the technical evaluator and the product reviewer.

## When to Use

- After completing a feature (self-check before moving on)
- When the user asks for a review, gut-check, or quality assessment
- Automatically as part of `/handoff` (Step 1 and Step 2)
- When you're uncertain whether work meets the bar

## Input

$ARGUMENTS

If arguments are provided, they describe the scope of the evaluation (e.g., "just the Compiler changes" or "the last 3 commits"). If no arguments, evaluate all work since the last session handoff or the last evaluation, whichever is more recent.

## Step 1 — Gather Context

Collect the information both reviewers need:

```bash
# Recent commits
git log --oneline -10

# Determine scope — commits since last handoff or last evaluation
# Look for the most recent session artifact for a reference point
ls -t docs/sessions/session-*.md 2>/dev/null | head -1
```

```bash
# Full diff for the evaluation scope
git diff HEAD~N  # where N = number of commits in scope
```

```bash
# Current phase
grep -m1 "Current Phase" docs/PHASE_STATUS.md 2>/dev/null || echo "Phase unknown"
```

Build a context summary:
- Phase number
- Commits in scope (hashes and messages)
- Files changed
- Deliverables these changes relate to (cross-reference with PHASE_STATUS.md)

## Step 2 — Invoke the Technical Evaluator

Invoke the `evaluator` subagent using the Agent tool with a prompt like:

"Evaluate the following work from Phase [N]. Commits: [list]. Changed files: [list]. Run your full evaluation procedure — Functionality, Test Quality, Code Quality, Completeness, and Integration."

Present the evaluator's full report without modification or softening.

## Step 3 — Invoke the Product Reviewer

Invoke the `product-reviewer` subagent using the Agent tool with a prompt like:

"Review the following work from Phase [N] for product quality. Commits: [list]. Changed files: [list]. Review against the product vision in docs/REQUIREMENTS.md and any content guides referenced in CLAUDE.md. Run your full review — Vision Alignment, User Experience, Content Quality, and Feature Depth."

Present the product reviewer's full report without modification or softening.

## Step 4 — Combined Summary

After both reports are presented, provide a brief combined summary:

```
═══ Evaluation Summary ═══

Technical:  [score]/5 — [PASS | PASS WITH ISSUES | FAIL]
Product:    [score]/5 — [PASS | NEEDS WORK]

Critical issues: [count, or "none"]
Major issues:    [count, or "none"]
Minor issues:    [count, or "none"]

Recommendation:  [proceed | fix before continuing | fix before handoff]
```

**Recommendation logic:**
- Any critical issue from either reviewer → "fix before continuing"
- Major issues only → "fix before handoff" (ok to continue building, but address before session end)
- Minor issues only or clean → "proceed"

## Notes

- Both reviewers are read-only. They inspect the code and report findings. They do not modify files.
- If this is invoked as part of `/handoff` and either reviewer returns critical issues, the handoff stops. Fix the issues and re-run `/handoff`.
- If invoked mid-session as a self-check, critical issues should be fixed before moving to the next feature. Major issues can be deferred to before handoff.
- Do not editorialize or soften either report. Present them as-is. The user needs honest assessment, not reassurance.