Give a quick status overview of the project without the full session initialization.

## Gather State

1. Run `test -f package.json && npm test 2>&1 || echo "NOT_SCAFFOLDED"` and capture pass/fail counts (or note project isn't scaffolded yet)
2. Run `git log --oneline -5` for recent activity (if git is initialized; otherwise note "no git history")
3. Read `docs/PHASE_STATUS.md` for phase completion state
4. Check `git status` for any uncommitted changes
5. List the most recent file in `docs/sessions/` and read its **Next Steps** section (if no session files exist, note "no prior sessions")

## Report

Present a concise summary:

- **Current phase:** N — [Name] — X of Y deliverables complete
- **Tests:** X passing, Y failing
- **Last commit:** [hash] [message] [time ago]
- **Uncommitted changes:** yes/no
- **Next up:** [the recommended next feature from the last handoff]

Keep this to 10 lines or fewer. This is a quick orientation, not a deep dive.
