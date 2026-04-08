Delegate a full QA evaluation to the evaluator subagent.

## What to Evaluate

$ARGUMENTS

If no arguments were provided, evaluate the work completed in the current session — use `git diff` and the most recent commits to identify what was changed.

## Instructions

Gather context before invoking the evaluator:

1. Read `docs/PHASE_STATUS.md` to get the current phase number
2. Run `git log --oneline -10` to identify recent commits
3. If evaluating the full session: run `git diff HEAD~N` (where N = number of session commits) to get the scope of changes
4. If evaluating a specific feature (from $ARGUMENTS): identify the relevant files and commits

Then invoke the `evaluator` subagent using the Agent tool with a prompt string like:

> Evaluate the following work from Phase [N]. [Description of what was built or changed]. Commits: [hashes]. Changed files: [list]. [Any specific concerns, e.g., "The event schema was modified — check that all consumers still match."]

The more context you give the evaluator in its prompt, the more targeted its review will be. Do not just say "evaluate recent work" — specify what to look at.

## After Evaluation

Once the evaluator returns its report, present it to the user without modification or softening. The evaluator's skepticism is intentional — do not undermine it by qualifying its output. Then:

1. **If FAIL:** List the critical issues that must be addressed. Do not proceed to new features until critical issues are resolved
2. **If PASS WITH ISSUES:** Note the issues but confirm it's safe to continue. Address the issues before the next session handoff if time permits
3. **If PASS:** Confirm the feature is complete and ready. Update `docs/PHASE_STATUS.md` to reflect the completed deliverable
