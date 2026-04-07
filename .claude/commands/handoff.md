End the current work session by running QA evaluation, generating a structured handoff artifact, and updating the phase tracker.

## Step 1 — Invoke the Evaluator

Before anything else, invoke the `evaluator` subagent using the Agent tool. Build the prompt string for the evaluator by gathering:

1. Run `git log --oneline -10` to identify this session's commits
2. Run `git diff HEAD~N` (where N = number of session commits) to get the full diff
3. Read `docs/PHASE_STATUS.md` for the current phase number

Then pass a prompt like: "Evaluate the following work from Phase [N]. Commits this session: [list]. The diff covers these files: [list changed files]. Run your full evaluation procedure."

Present the evaluator's full report to the user without modification or softening.

- **If FAIL:** Stop the handoff here. Fix the critical issues identified by the evaluator, then invoke `/handoff` again from the top (the evaluator will re-run on the fixed code).
- **If PASS WITH ISSUES:** Note the issues but continue with Step 2. Issues will be captured in the handoff artifact.
- **If PASS:** Continue with Step 2.

## Step 2 — Final Test Run

Run the full test suite to confirm the codebase is in a clean state:

```
npm test 2>&1
```

If any tests are failing, note them explicitly in the handoff. Do not leave the session with unexplained test failures.

## Step 3 — Commit Any Uncommitted Work

Check for uncommitted changes:

```
git status
```

If there are uncommitted changes, commit them with an appropriate conventional commit message. If there are changes that are intentionally uncommitted (work in progress, experimental code), note this in the handoff artifact.

## Step 4 — Review Session Work

Review what was accomplished this session. Use a reasonable number of recent commits:

```
git log --oneline -15
```

Scan the output and identify which commits belong to this session (based on timestamps and commit messages). If the session spans more than 15 commits, increase the count.

## Step 5 — Generate Handoff Artifact

Determine the next session number by checking existing files in `docs/sessions/`. Create the handoff artifact at:

```
docs/sessions/session-YYYY-MM-DD-NNN.md
```

Where YYYY-MM-DD is today's date and NNN is a zero-padded sequence number (001, 002, etc.) for the day.

The handoff artifact must contain:

```markdown
# Session Handoff — YYYY-MM-DD-NNN

**Phase:** N — [Phase Name]
**Date:** YYYY-MM-DD

## Completed This Session

For each feature completed, include:
- What was built (brief description)
- Commit hash(es)
- Tests added (count and what they cover)
- Any notable implementation decisions and why they were made

## In Progress

Anything started but not finished:
- What it is
- Current state (what's done, what remains)
- Where to pick up (specific file and function/component)

## Blocked

Anything that can't proceed and why:
- The blocker
- What's needed to unblock it
- Whether it blocks other work

## Issues & Technical Debt

Any issues identified (by you or the evaluator) that weren't resolved this session:
- Issue description
- Severity (critical / important / minor)
- Where it lives in the code

## Evaluator Results

Summary of the evaluator's assessment:
- Weighted score: X.X/5.0
- Verdict: PASS / PASS WITH ISSUES / FAIL
- Critical issues (if any): [list]
- Unresolved important issues: [list]

## Test State

- Total tests: N
- Passing: N
- Failing: N (list which ones and why)
- Skipped: N
- Coverage: N% (if coverage reporting is configured)

## Build State

- Build: clean / errors / warnings
- Lint: clean / errors / warnings
- TypeScript: strict compliance / issues noted

## Next Steps

The logical next feature(s) to tackle in the next session, in priority order:
1. [Feature] — [why it's next] — [estimated complexity: small/medium/large]
2. [Feature] — [why it's next] — [estimated complexity: small/medium/large]

## Session Notes

Any context that would be useful for the next session that doesn't fit above:
- Architecture decisions made and rationale
- Patterns established that should be followed
- External dependencies or environment setup changes
- Gotchas discovered
```

## Step 6 — Update Phase Status

Update `docs/PHASE_STATUS.md` to reflect the current state of the phase:
- Mark completed deliverables
- Update any progress notes
- Adjust estimates if the work revealed unexpected complexity

## Step 7 — Summary

After writing the handoff artifact and updating the phase status, present a brief summary:
- What was accomplished this session (1-3 sentences)
- Current overall phase progress (e.g., "Phase 1: 6 of 9 deliverables complete")
- The recommended starting point for the next session
