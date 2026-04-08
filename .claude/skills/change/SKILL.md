---
name: change
description: "Classify in-phase feedback (bug fix, quality improvement, or new capability) and route through the correct workflow. Use when the user reports something broken, requests a change to how a feature works, or asks for something new."
user-invocable: true
---

# Change — In-Phase Feedback Router

Process feedback on the current phase's work and route it through the correct workflow.

## Input

$ARGUMENTS

This should describe what needs to change — a bug you found, a quality improvement you want, or a new capability to add. If no arguments are provided, ask what the feedback is.

## Step 1 — Classify

Before doing anything, classify the feedback into one of three categories:

### Bug Fix
The deliverable doesn't work as specified. The spec already defines the correct behavior; the implementation is wrong.

**Signals:** "X is broken", "this should do Y but it does Z", "there's an error when...", "the output is wrong", a traceback, a test failure, a regression.

**The test:** Does the existing spec/deliverable already describe the correct behavior? If yes → bug fix.

### Quality Improvement
The definition of "done" for an existing deliverable needs to change. This shifts what the deliverable means, not just whether it works.

**Signals:** "X should also do Y", "the approach to X needs to change", "X would be better if...", "I want X to work differently", a fundamental shift in how a feature operates.

**The test:** Does this change what the deliverable means? Would a future session, reading the current spec, implement something different from what you now want? If yes → quality improvement.

### New Capability
An entirely new deliverable that wasn't in the original plan.

**Signals:** "We need a new command for...", "add support for X", "I want a feature that...", something with no corresponding deliverable in REQUIREMENTS.md.

**The test:** Is there an existing deliverable this maps to? If no → new capability.

## Step 2 — Confirm Classification

Present the classification to the user:

```
Classification: [Bug Fix | Quality Improvement | New Capability]
Rationale: [one sentence explaining why this category]
Affected deliverable: [which deliverable in REQUIREMENTS.md, or "new" for new capabilities]
```

Wait for the user to confirm before proceeding. They may reclassify — if someone says "this is actually a quality improvement, not a bug fix," follow their classification.

## Step 3 — Execute

### Bug Fix Path

1. Write a failing test that reproduces the bug
2. Fix the implementation
3. Verify the test passes
4. Run the full test suite to check for regressions
5. Commit with `fix(scope): description of what was wrong`
6. Note in the session handoff under **Completed**

No doc updates needed — the spec already describes the correct behavior.

### Quality Improvement Path

1. **Update docs first:**
   - Update the affected deliverable's wording in `docs/REQUIREMENTS.md` to reflect the new definition
   - Update `docs/ARCHITECTURE.md` if the change affects technical design
   - Update `docs/PHASE_STATUS.md` if the deliverable wording changed (keep the same status marker)
   - Present the doc changes to the user for approval before implementing
2. **Then implement:**
   - Write tests for the new behavior
   - Implement the change
   - Run the full test suite
   - Commit the doc updates and implementation together: `refactor(scope): description` or `feat(scope): description` depending on scope
3. Note in the session handoff under **Completed** with a reference to the doc changes

### New Capability Path

1. **Update docs first:**
   - Add the new deliverable to the appropriate phase in `docs/REQUIREMENTS.md`
   - Add to `docs/PHASE_STATUS.md` with ⬜ status
   - Update `docs/ARCHITECTURE.md` if it introduces new components or data flows
   - Present the doc changes to the user for approval before implementing
2. **Then implement** using the standard red/green TDD workflow
3. Commit with `feat(scope): description`
4. Update `docs/PHASE_STATUS.md` to ✅ when complete

## Reminders

- Multiple pieces of feedback can be processed in one session. Classify each one independently.
- A single piece of feedback might contain both a bug fix and a quality improvement. Split them — fix the bug first (no doc ceremony), then process the improvement (doc-first).
- If you're unsure whether something is a bug fix or a quality improvement, default to quality improvement. It's better to update docs unnecessarily than to let the spec drift silently.
- If the feedback is about something in a future phase, note it in `docs/sessions/` under **Session Notes** for the relevant phase. Don't implement across phase boundaries.