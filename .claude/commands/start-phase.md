Read the project context and prepare for a focused work session on Phase $ARGUMENTS.

If no phase number was provided (i.e., $ARGUMENTS is empty), read `docs/PHASE_STATUS.md` to determine the current phase and use that. If the phase number doesn't match a phase in PHASE_STATUS.md (1-9), ask for clarification before proceeding.

## Step 1 — Run the Tests

Check if the project has been scaffolded:

```
test -f package.json && npm test 2>&1 || echo "NO_PACKAGE_JSON"
```

- **If tests run:** Record the results — total tests, passing, failing, skipped. If any tests are failing, note them — you must not introduce additional failures during this session.
- **If `NO_PACKAGE_JSON`:** The project hasn't been scaffolded yet. This is expected for the very first session. Skip to Step 2 and note that scaffolding is the first deliverable. See the "Bootstrapping" section in CLAUDE.md for scaffolding requirements.

## Step 2 — Load Phase Context

Read these files in order:

1. `docs/PHASE_STATUS.md` — current completion state across all phases
2. `docs/REQUIREMENTS.md` — find the section for Phase $ARGUMENTS and read the full deliverables list
3. `docs/ARCHITECTURE.md` — read the sections relevant to Phase $ARGUMENTS
4. The most recent file in `docs/sessions/` — the last session's handoff artifact

## Step 3 — Review Recent Git History

```
git log --oneline -15
```

Use this to understand what was worked on recently and what state the codebase is in.

## Step 4 — Assess Current State

Based on what you've read, produce a brief status summary:

- **Phase $ARGUMENTS progress:** what deliverables are complete, what remains
- **Test baseline:** X passing, Y failing, Z skipped
- **Last session:** what was done, what was left in progress or blocked
- **Codebase state:** clean build? any outstanding issues?

## Step 5 — Plan This Session

Identify the next feature or deliverable to work on within Phase $ARGUMENTS. State:

1. **What you'll build** — the specific feature or deliverable
2. **How you'll test it** — the tests you'll write first (red/green TDD)
3. **Integration points** — what existing code this touches, what events it should fire
4. **Definition of done** — how we'll know this feature is complete

**In interactive mode:** Wait for the user to approve the plan before starting implementation. Do not begin coding until the plan is confirmed or adjusted.

**In headless/bypass mode:** Present the plan, then proceed to implementation. The plan is logged in the session transcript for post-hoc review. If the task was provided via a prompt (e.g., `make prompt P="..."`), treat the prompt as pre-approved scope and plan accordingly.

## Reminders

- Use red/green TDD for every feature. Write the test first, watch it fail, then implement.
- Work on one feature at a time. Complete it (including tests) before moving to the next.
- Commit after each completed feature with a descriptive conventional commit message.
- Do not implement features from phases other than Phase $ARGUMENTS.
- If you encounter a decision point with multiple valid approaches, pause and explain the tradeoffs.
