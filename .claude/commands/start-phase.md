Read the project context and prepare for a focused work session on Phase $ARGUMENTS.

If no phase number was provided (i.e., $ARGUMENTS is empty), read `docs/PHASE_STATUS.md` to determine the current phase and use that. If the phase number doesn't match a phase in PHASE_STATUS.md, ask for clarification before proceeding.

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

## Step 3 — Check Manual Tasks

Check if `docs/manual/` exists and contains any task cards or scripts:

```
ls docs/manual/task-*.md docs/manual/task-*.sh 2>/dev/null
```

If manual tasks exist, read each one and check the **Status** field (in the header comment for scripts, in the frontmatter for cards):

- **`pending`** — the human hasn't done this yet. Note it in the status summary. If it blocks a deliverable, do not plan work on that deliverable.
- **`done`** — the human completed it. Read the **Notes** field for any information the agent needs (configuration values, URLs, unexpected outcomes). If the task was blocking a deliverable, that deliverable is now unblocked.
- **`blocked`** — the human tried but hit a problem. Read the Notes for details. Flag this in the status summary.

## Step 4 — Review Recent Git History

```
git log --oneline -15
```

Use this to understand what was worked on recently and what state the codebase is in.

## Step 5 — Spec Alignment Check

Check if an original spec or PRD exists. Look for common locations:

```
ls docs/SPEC.md docs/spec.md docs/PRD.md docs/prd.md 2>/dev/null
```

Also check CLAUDE.md's References section for any referenced spec files.

**If a spec exists:** Invoke the `product-reviewer` subagent with a targeted prompt:

"Compare the Phase [N] deliverables in docs/REQUIREMENTS.md against the original spec at [path]. For each incomplete deliverable (⬜ or 🔄 in PHASE_STATUS.md) that the agent is about to work on this session, flag anything that was thinned out, oversimplified, or lost in translation from the spec. Don't review the whole project or completed deliverables — just what's in scope for this session. Be specific: quote the spec and quote the requirement side by side where there's a gap."

Review the product reviewer's findings. If it identifies gaps, update the project docs immediately to close them:

- **Thin deliverables:** where the requirement is a pale summary of a richer spec description, update the deliverable's wording in `docs/REQUIREMENTS.md` to capture the spec's full intent. Update `docs/PHASE_STATUS.md` to match the revised wording. If the spec describes architectural detail that's missing, add it to `docs/ARCHITECTURE.md`.
- **Drifted deliverables:** where the requirement says something different from the spec, correct `docs/REQUIREMENTS.md` to realign with the spec. Update `docs/PHASE_STATUS.md` and `docs/ARCHITECTURE.md` accordingly.
- **Missing deliverables:** where the spec describes functionality that has no corresponding requirement, add the deliverable to the appropriate phase in `docs/REQUIREMENTS.md`. Add it to `docs/PHASE_STATUS.md` with ⬜ status. Update `docs/ARCHITECTURE.md` if it introduces new components or data flows.

Commit the doc updates: `docs: fortify Phase N requirements from spec alignment review`

These updates ensure the identified gaps are captured in the project's permanent record, not just in the agent's session plan. The session plan in Step 7 then works from the fortified docs.

**If no spec exists:** Skip this step. The requirements and architecture docs are the source of truth.

## Step 6 — Assess Current State

Based on what you've read, produce a brief status summary:

- **Phase $ARGUMENTS progress:** what deliverables are complete, what remains
- **Test baseline:** X passing, Y failing, Z skipped
- **Last session:** what was done, what was left in progress or blocked
- **Manual tasks:** any pending or blocked manual tasks, and what they affect
- **Spec alignment:** gaps found and docs updated (list what changed), or "no spec found" / "aligned"
- **Codebase state:** clean build? any outstanding issues?

## Step 7 — Plan This Session

Identify the next feature or deliverable to work on within Phase $ARGUMENTS. State:

1. **What you'll build** — the specific feature or deliverable
2. **Spec depth** — if the docs were fortified in Step 5, state how the updated requirements change the scope or approach compared to what was there before
3. **How you'll test it** — the tests you'll write first (red/green TDD)
4. **Integration points** — what existing code this touches
5. **Definition of done** — how we'll know this feature is complete

**In interactive mode:** Wait for the user to approve the plan before starting implementation. Do not begin coding until the plan is confirmed or adjusted.

**In headless/bypass mode:** Present the plan, then proceed to implementation. The plan is logged in the session transcript for post-hoc review. If the task was provided via a prompt (e.g., `make prompt P="..."`), treat the prompt as pre-approved scope and plan accordingly.

## Reminders

- Use red/green TDD for every feature. Write the test first, watch it fail, then implement.
- Work on one feature at a time. Complete it (including tests) before moving to the next.
- Commit after each completed feature with a descriptive conventional commit message.
- Do not implement features from future phases. Fixes and improvements to prior phase deliverables are encouraged when the current phase's work reveals gaps.
- If you encounter a decision point with multiple valid approaches, pause and explain the tradeoffs.
