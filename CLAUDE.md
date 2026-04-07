# [PROJECT NAME]

## Project Identity

[Describe what this project is, who it's for, and what makes it distinctive. 2-3 sentences.]

## Tech Stack

- **Framework:** [e.g., Next.js 14+, App Router, TypeScript strict, Tailwind CSS]
- **Testing:** [e.g., Jest + React Testing Library, Playwright for E2E]
- **Package Manager:** [e.g., npm, pnpm, yarn]
- **Hosting:** [e.g., Vercel, Cloud Run, Netlify]
- [Add other stack components as needed]

## Current Phase

**Phase 1 — [Phase Name]**

See `docs/REQUIREMENTS.md` for the full development plan.
See `docs/ARCHITECTURE.md` for technical architecture details.
See `docs/PHASE_STATUS.md` for current completion state.

Work on the current phase only. Do not implement features from future phases. If you encounter a dependency on a future phase, note it in your session handoff and move on.

Do not modify sections of this file other than "Current Phase" unless explicitly asked to.

### Bootstrapping (First Session Only)

If this is the very first session and no `package.json` exists yet, the project hasn't been scaffolded. The first task is to initialize the project. Until scaffolding is complete:

- `npm test`, `npm run build`, and `npm run lint` will fail — this is expected
- Skip the "Run the Tests" step in `/start-phase` and note that scaffolding is the first deliverable
- During scaffolding, configure the following:
  - [Framework and language setup]
  - **Test runner** with appropriate libraries for your stack
  - **Linter** configured for your language/framework
  - **Formatter** (the auto-format hook depends on a formatter being installed)
  - Path aliases if applicable
  - Scripts in `package.json`: `test`, `test:watch`, `test:coverage`, `lint`, `build`, `dev`
- Write at least one passing test before ending the first session — this establishes the test baseline for all future sessions

## Directory Structure

```
[project]/
├── CLAUDE.md                    # This file — project context for Claude Code
├── docs/
│   ├── REQUIREMENTS.md          # Full development plan
│   ├── ARCHITECTURE.md          # Technical architecture
│   ├── PHASE_STATUS.md          # Living phase completion tracker
│   └── sessions/               # Session handoff artifacts
├── src/                        # Source code
├── tests/                      # Test files
├── public/                     # Static assets (if applicable)
├── .claude/                    # Claude Code configuration
│   ├── settings.json
│   ├── agents/
│   ├── commands/
│   └── skills/
└── sandbox/                    # Docker sandbox for autonomous mode
```

## Testing

### First, Run the Tests

At the start of every session, before doing anything else, run:

```
npm test
```

This anchors you in the current state of the codebase. It tells you how many tests exist, whether anything is broken, and puts you in a testing mindset for the session.

### Red/Green TDD

Use red/green TDD for every feature:

1. **Write the test first** — define what the feature should do
2. **Run the test and watch it fail** (red) — confirm the test is actually testing something
3. **Implement the minimum code to make it pass** (green)
4. **Refactor** if needed, re-running tests to confirm nothing breaks

This is non-negotiable. Every new feature, component, utility function, API route, and event handler gets a test written before the implementation.

### Test Commands

```bash
npm test                    # Run all tests
npm test -- --watch         # Watch mode during development
npm test -- --coverage      # Coverage report
```

## Coding Standards

### General

- Strict type checking. No `any` types. No type-ignore directives without a comment explaining why.
- All async operations must have error handling. No unhandled promise rejections.
- Use descriptive names. Clarity over brevity.

[Add project-specific coding standards here: language conventions, framework patterns, import ordering, etc.]

### Error Handling

- User-facing errors show a meaningful message. Technical details go to the console / error reporting.
- API routes return appropriate HTTP status codes and structured error responses.

## Git Conventions

### Commit Frequency

Commit after each completed feature or meaningful unit of work within a session. Small, frequent commits with descriptive messages. Each commit should leave the codebase in a working state (tests pass).

### Commit Messages

Use conventional commits format:

```
feat(component): add new feature
fix(module): correct specific bug
test(feature): add red/green tests for feature
docs(section): update documentation
chore(deps): upgrade dependency
refactor(module): restructure without behavior change
```

### Branching

- `main` — production-ready code
- `phase/N-name` — branch per phase
- `feat/description` — feature branches off the phase branch for larger features
- Merge feature branches into the phase branch. Merge the phase branch into `main` when the phase is complete and evaluated.

### Session Context from Git

When resuming work, reviewing recent git history is a fast way to rebuild context:

```
git log --oneline -20
```

This is complementary to reading the session handoff artifact — use git log for quick orientation, read the handoff doc for detailed state.

## Session Workflow

### Starting a Session

1. **Run the tests:** `npm test` — establish baseline
2. **Load context:** Read `docs/PHASE_STATUS.md` and the latest file in `docs/sessions/`
3. **Review recent changes:** `git log --oneline -10` to orient on recent work
4. **Plan:** Identify the next feature to implement within the current phase. State what you'll build and how you'll test it before writing code

### During a Session

- Work on **one feature at a time**. Complete it (including tests) before starting the next
- **After each completed feature, run a self-check:**
  1. `npm test` — all tests pass, no regressions
  2. `npm run build` — clean compile, no type errors
  3. Verify: no `any` types introduced, no TODO/FIXME left unresolved, no stubbed implementations
  4. If any check fails, fix before moving to the next feature
- Commit after each completed feature (after the self-check passes)
- If you encounter a decision point with multiple valid approaches, pause and explain the tradeoffs. Do not pick one silently

### Ending a Session

- **Invoke the evaluator subagent** (`@evaluator`) for an independent QA assessment of all work completed this session. Present the evaluator's full report without softening or editorializing. If the evaluator returns a FAIL verdict, address the critical issues before proceeding to handoff. You can also invoke `/evaluate` manually mid-session on specific features if you want earlier feedback
- Run the full test suite one final time
- Commit any uncommitted work
- Generate a session handoff artifact at `docs/sessions/session-YYYY-MM-DD-NNN.md` containing:
  - **Completed:** what was built this session, with commit references
  - **In Progress:** anything started but not finished
  - **Blocked:** anything that can't proceed and why
  - **Evaluator Results:** summary of the evaluator's scores and any unresolved issues
  - **Test State:** number of tests, all passing/any failing
  - **Next Steps:** the logical next feature(s) to tackle
- Update `docs/PHASE_STATUS.md` with current completion state

### Session Artifact Conventions

When **writing** handoff artifacts, be concrete: include commit hashes, test counts, specific file paths. Don't omit problems — if you cut a corner or stubbed something, say so. Keep "Next Steps" specific enough to start implementing immediately.

When **reading** handoff artifacts, prioritize: In Progress → Blocked → Next Steps → Evaluator Results. These determine what happens next. If unresolved critical issues from the evaluator exist, address those before new feature work.

When **updating PHASE_STATUS.md**, use the format: `✅ YYYY-MM-DD, session-YYYY-MM-DD-NNN` for completed deliverables. Update the "Last updated" header line with the current date and session reference. See `.claude/skills/session-management/SKILL.md` for additional conventions on context continuity patterns across different gap durations.

## References

- `docs/REQUIREMENTS.md` — full development plan with deliverables and dependencies
- `docs/ARCHITECTURE.md` — technical architecture and data flow specifications
- `docs/PHASE_STATUS.md` — living tracker of phase completion
- `docs/sessions/` — session handoff artifacts with detailed state from prior work sessions
- `.claude/agents/evaluator.md` — QA/evaluator subagent for post-feature evaluation
- `.claude/commands/` — session workflow commands (`/start-phase`, `/evaluate`, `/handoff`, `/status`)
- `.claude/settings.json` — project-level permissions and hooks (committed to git, shared)
- `.claude/settings.local.json` — personal permission overrides (gitignored). Use this for machine-specific settings. Local scope overrides project scope
- `.claude/hooks/` — deterministic enforcement scripts (bash-guard, auto-format, stop-check)
- `sandbox/` — Docker sandbox for running Claude Code with `--dangerously-skip-permissions`

### Security Model

Permissions, hooks, and the Docker sandbox form three layers of defense:

1. **Permissions** (settings.json) — auto-allow safe commands, auto-deny known-bad patterns. Convenience layer — reduces permission prompts for routine work
2. **Hooks** (bash-guard.sh) — deterministic enforcement of dangerous patterns. Works both inside and outside Docker. Blocks destructive commands, git push, gcloud delete operations
3. **Docker sandbox** (optional) — network-level isolation via iptables firewall. Blocks all non-allowlisted outbound traffic. Only needed for `--dangerously-skip-permissions` mode

The Write and Edit permissions in settings.json are scoped to project directories. If you need to write to an unlisted path, add it to `.claude/settings.local.json`.
