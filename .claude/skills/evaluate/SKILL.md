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
═══ Evaluation Summary (Pass N) ═══

Technical:  [score]/5 — [PASS | PASS WITH ISSUES | FAIL]
Product:    [score]/5 — [PASS | NEEDS WORK]

Critical issues: [count, or "none"]
Major issues:    [count, or "none"]
Minor issues:    [count, or "none"]

Action:  [fix and re-evaluate | proceed ✓]
```

**Recommendation logic:**
- Any critical issue from either reviewer → "fix and re-evaluate"
- Major issues → "fix and re-evaluate"
- Minor issues only → "fix and re-evaluate"
- Clean (no issues) → "proceed"

## Step 5 — Fix and Re-Evaluate Loop

**Evaluation is iterative, not a single pass.** If the combined summary has any issues (Critical, Major, or Minor), fix them — do not log them and move on.

1. Work through the issues in severity order: Critical → Major → Minor
2. Fix each issue, run the relevant tests to confirm the fix
3. Commit the fixes: `fix(scope): address evaluation finding — [description]`
4. After all issues from the current pass are fixed, re-invoke Steps 2-4 (both reviewers, fresh evaluation of the updated code)
5. Repeat until the evaluation is clean

**The loop terminates when:**
- Both reviewers return no issues → proceed to the next feature or to `/handoff`
- The user explicitly defers specific issues (e.g., "skip the minor formatting issues for now") → proceed, but note deferred issues in the session handoff under Issues & Technical Debt with the reason for deferral

**Do not:**
- Present issues and ask "should I fix these?" — fix them. The default is to fix.
- Treat Major or Minor issues as acceptable debt. They are work items, not documentation items.
- Move to the next feature with unresolved issues from evaluation unless the user explicitly approves deferral.
- Argue that issues are "non-blocking" or "cosmetic" as a reason to skip them. If the reviewer flagged it, it matters.

**Context budget awareness:** If the context window is getting long after multiple passes, note the remaining issues in the session handoff with the tag `[deferred: context limit]` so the next session picks them up immediately. This is the only acceptable automatic deferral.

## Notes

- Both reviewers are read-only. They inspect the code and report findings. They do not modify files.
- If this is invoked as part of `/handoff` and either reviewer returns critical issues, the handoff stops. Fix the issues and re-run `/handoff`.
- Do not editorialize or soften either report. Present them as-is. The user needs honest assessment, not reassurance.
- The iterative loop is the default behavior. The agent should expect multiple passes — a first evaluation rarely comes back clean, and that's normal. The goal is zero debt at the feature boundary, not forward progress at the cost of quality.