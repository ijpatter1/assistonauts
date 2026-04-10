End the current work session by running QA evaluation, generating a structured handoff artifact, and updating the phase tracker.

## Step 1 — Invoke the Evaluator

Before anything else, invoke the `evaluator` subagent using the Agent tool. Build the prompt string for the evaluator by gathering:

1. Run `git log --oneline -10` to identify this session's commits
2. Run `git diff HEAD~N` (where N = number of session commits) to get the full diff
3. Read `docs/PHASE_STATUS.md` for the current phase number

Then pass a prompt like: "Evaluate the following work from Phase [N]. Commits this session: [list]. The diff covers these files: [list changed files]. Run your full evaluation procedure."

Present the evaluator's full report to the user without modification or softening.

- **If FAIL:** Stop the handoff here. Fix the critical issues identified by the evaluator, then invoke `/handoff` again from the top (the evaluator will re-run on the fixed code).
- **If PASS WITH ISSUES:** Note the issues but continue with Step 2.
- **If PASS:** Continue with Step 2.

## Step 2 — Invoke the Product Reviewer

Invoke the `product-reviewer` subagent using the Agent tool. Pass a prompt like: "Review the following work from Phase [N] for product quality. Commits this session: [list]. Changed files: [list]. Review against the product vision in docs/REQUIREMENTS.md and any content guides referenced in CLAUDE.md."

Present the product reviewer's full report to the user without modification or softening.

- **If NEEDS WORK with Critical issues:** Stop the handoff. Address critical product issues, then invoke `/handoff` again.
- **If NEEDS WORK with Major/Minor issues only:** Note the issues but continue with Step 3. Issues will be captured in the handoff artifact.
- **If PASS:** Continue with Step 3.

## Step 3 — Final Test Run

Run the full test suite to confirm the codebase is in a clean state:

```
npm test 2>&1
```

If any tests are failing, note them explicitly in the handoff. Do not leave the session with unexplained test failures.

## Step 4 — Commit Any Uncommitted Work

Check for uncommitted changes:

```
git status
```

If there are uncommitted changes, commit them with an appropriate conventional commit message. If there are changes that are intentionally uncommitted (work in progress, experimental code), note this in the handoff artifact.

## Step 5 — Review Session Work

Review what was accomplished this session. Use a reasonable number of recent commits:

```
git log --oneline -15
```

Scan the output and identify which commits belong to this session (based on timestamps and commit messages). If the session spans more than 15 commits, increase the count.

## Step 6 — Generate Handoff Artifact

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

Any issues identified (by you or either reviewer) that weren't resolved this session:
- Issue description
- Severity (critical / important / minor)
- Source (evaluator / product reviewer / self-identified)
- Where it lives in the code

## Evaluator Results

Summary of the evaluator's technical assessment:
- Weighted score: X.X/5.0
- Verdict: PASS / PASS WITH ISSUES / FAIL
- Critical issues (if any): [list]
- Unresolved important issues: [list]

## Product Review Results

Summary of the product reviewer's assessment:
- Weighted score: X.X/5.0
- Verdict: PASS / NEEDS WORK
- Vision alignment: [score]/5
- User experience: [score]/5
- Content quality: [score]/5
- Feature depth: [score]/5
- Issues (if any): [list]

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

## Step 7 — Update Phase Status

Update `docs/PHASE_STATUS.md` to reflect the current state of the phase:
- Mark completed deliverables
- Update any progress notes
- Adjust estimates if the work revealed unexpected complexity

## Step 8 — Phase Completion: Generate UAT Plan

**This step is conditional.** Check if all deliverables for the current phase are now ✅ in `docs/PHASE_STATUS.md`. If any deliverables are still ⬜, 🔄, or ❌, skip to Step 9.

If the phase is complete, generate a user acceptance testing plan. The UAT plan verifies that the phase's deliverables work end-to-end as a user would experience them — not unit test coverage (the evaluator handles that) or spec alignment (the product reviewer handles that), but real-world workflows from start to finish.

### Generating the UAT Plan

Invoke the `product-reviewer` subagent with a prompt like: "Phase [N] is dev complete. All deliverables have passed technical evaluation and product review. Generate end-to-end user acceptance scenarios that test the phase's deliverables as a user would experience them. Reference docs/REQUIREMENTS.md for the deliverables, docs/ARCHITECTURE.md for the technical design, and any content guides or specs referenced in CLAUDE.md. Focus on realistic workflows, not individual feature checks — each scenario should exercise multiple deliverables working together."

Use the product reviewer's scenarios to produce the UAT artifact. **Follow the same automation-first hierarchy as `/manual`:**

1. **If the project is a CLI tool or backend service:** Produce a UAT script at `docs/uat/phase-N-uat.sh`. The script should set up prerequisites, run each scenario, pause for human observation where visual verification is needed, collect pass/fail results, and print a summary. Use the same `verify()` pattern from the `/manual` script template for automated checks. For steps requiring human judgment, use a `confirm()` helper:

```bash
confirm() {
  echo ""
  echo "  → $1"
  read -p "  Pass? [Y/n] " -n 1 -r
  echo ""
  if [[ $REPLY =~ ^[Nn]$ ]]; then
    echo "  ✗ $2"; ((FAIL++))
  else
    echo "  ✓ $2"; ((PASS++))
  fi
}

# Example usage:
confirm "Does the dashboard show campaign data for all 3 channels?" \
  "Dashboard displays multi-channel data"
```

2. **If the project is a web UI:** Produce a UAT script that automates setup and verification where possible, and uses `confirm()` prompts for visual/interactive checks. Include `open` commands to launch the relevant pages. Structure the script as a guided walkthrough — the human follows along while the script manages state and collects results.

3. **If the project is purely manual to test:** Produce a UAT task card at `docs/uat/phase-N-uat.md` with numbered scenarios, each containing steps, expected outcomes, and pass/fail checkboxes. This is the last resort.

### UAT Artifact Structure

Whether script or card, each UAT plan should cover:

- **Prerequisites** — what must be running, configured, or seeded before testing
- **Scenarios** — numbered end-to-end workflows, each testing multiple deliverables together. Each scenario has:
  - A name and description of what it validates
  - Steps (automated where possible, guided where not)
  - Expected outcomes with concrete checks
  - Which deliverables it exercises
- **Edge cases** — at least 2-3 scenarios that test boundaries, error states, or non-obvious flows
- **Results summary** — pass/fail counts with a clear overall verdict

### After Generating UAT

Make the script executable if applicable:

```bash
chmod +x docs/uat/phase-N-uat.sh
```

Note in the handoff artifact under **Next Steps** that UAT is ready to run:

```
1. Run Phase N UAT: `bash docs/uat/phase-N-uat.sh`
2. [Next phase planning — if UAT passes]
```

The phase is not considered accepted until UAT passes. The next session's `/start-phase` should check for UAT results before starting new phase work.

## Step 9 — CLAUDE.md Freshness Check

Review the current CLAUDE.md against what actually happened during this session. Check for:

- **Tech stack drift:** Were new dependencies added, tools changed, or frameworks swapped? Does the Tech Stack section still reflect reality?
- **Directory structure changes:** Were new directories created that aren't in the Directory Structure section?
- **New conventions established:** Did you establish a pattern (naming convention, component structure, error handling approach) that future sessions should follow but that isn't documented in Coding Standards?
- **Phase progression:** If a phase was completed, does Current Phase need to advance?
- **Stale bootstrapping section:** If the project has been scaffolded, is the Bootstrapping section still present? It can be removed or collapsed once it's no longer the first session.
- **New references:** Were new reference documents created (content guides, API specs, data schemas) that should be listed in References?

If any updates are needed, **propose them to the user** as a list:

```
CLAUDE.md updates needed:
1. Tech Stack: add "sqlite-vec 0.1.6" to dependencies
2. Directory Structure: add "src/agents/" and "src/toolkits/"
3. Coding Standards: add "Agent classes use @mission decorator for toolkit methods"
4. Current Phase: advance to Phase 2
```

**In interactive mode:** Wait for approval before making the changes.
**In headless/bypass mode:** Apply the changes and note them in the handoff artifact under Session Notes.

If no updates are needed, skip this step silently — do not announce "CLAUDE.md is up to date."

## Step 10 — Summary

After writing the handoff artifact and updating the phase status, present a brief summary:
- What was accomplished this session (1-3 sentences)
- Current overall phase progress (e.g., "Phase 1: 6 of 9 deliverables complete")
- If UAT was generated: "Phase N UAT plan ready at `docs/uat/phase-N-uat.sh` — run before starting Phase N+1"
- The recommended starting point for the next session