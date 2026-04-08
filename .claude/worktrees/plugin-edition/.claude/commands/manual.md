Generate a manual task card for work that must be performed outside the sandbox.

Use this when you've done everything possible inside the sandbox but the remaining step requires human action — deploying, configuring a third-party UI, testing on a real device, running a command that needs network access beyond the firewall, etc.

## What to Generate

$ARGUMENTS

If no arguments are provided, describe what you just completed and what manual step remains.

## Task Card Format

Create a file at `docs/manual/task-YYYY-MM-DD-NNN.md` where NNN is a zero-padded sequence number for the day. Create the `docs/manual/` directory if it doesn't exist.

```markdown
# Manual Task — [Short Title]

**Created:** YYYY-MM-DD, session-YYYY-MM-DD-NNN
**Phase:** N
**Status:** pending
**Priority:** [high | medium | low]
**Blocks:** [what downstream work is blocked until this is done, or "nothing"]

## Context

[What the agent did inside the sandbox that led to this task. Include specific files created or modified, commits, and the current state. The human should understand exactly where things stand without reading the full session history.]

## Steps

[Numbered, specific steps the human needs to perform. Include exact commands, URLs, UI navigation paths, and expected outcomes. Be as precise as possible — the human may be doing this hours or days after the agent generated this card.]

1. [Step]
   - Expected result: [what they should see]
2. [Step]
   - Expected result: [what they should see]

## Verification

[How to confirm the task was completed successfully. Include specific checks the human should run.]

- [ ] [Verification check 1]
- [ ] [Verification check 2]

## Report Back

When complete, update the **Status** field above to `done` and add:

**Completed:** YYYY-MM-DD
**Notes:** [any observations, unexpected outcomes, or configuration values the agent needs to know]

If something didn't work as expected, set Status to `blocked` and describe what happened in Notes. The agent will read this on the next session start.
```

## Rules

- Be extremely specific in the Steps section. "Deploy to Vercel" is bad. "Run `vercel --prod` from the project root, or push to the `main` branch which triggers auto-deployment via the GitHub integration. The deployment URL will be https://iampatterson.com or the preview URL Vercel assigns" is good.
- Include any credentials, IDs, or configuration values the human will need. If these are sensitive, reference where to find them rather than writing them inline.
- If the task involves a third-party UI (GTM, Cookiebot, Stape, GCP Console), include the exact navigation path: "Go to tagmanager.google.com → Account 6346433751 → Container → Tags → New"
- State what's blocked. If nothing downstream depends on this, say so — it helps the human prioritize.
- The Verification section should include checks the human can run locally, not just "confirm it looks right." Prefer `curl` commands, URL checks, or specific log entries over visual inspection.

## After Creating the Task Card

1. Note the task in the current session's handoff artifact under **Blocked** or **In Progress** with a reference to the task card file
2. If the task blocks the current phase deliverable, mark that deliverable as ❌ in PHASE_STATUS.md with a reference to the task card
3. Continue working on other deliverables that aren't blocked by this task
4. Inform the user that a manual task card has been created and where to find it
