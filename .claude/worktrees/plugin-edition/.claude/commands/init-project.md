Scaffold the project documentation from a PRD or spec document.

## Input

$ARGUMENTS

This should be a file path to a PRD, spec, or design document. Read the entire file before proceeding.

If no file path is provided, check the workspace for common spec file patterns: `*spec*`, `*prd*`, `*requirements*`, `*design*` in the root or `docs/` directory. If found, confirm with the user before proceeding. If nothing is found, ask for the file path.

## Process

Read the spec document thoroughly, then generate the four project-specific files in sequence. Each file builds on the previous one — do not generate them in parallel.

### Step 1 — Analyze the Spec

Before writing any files, extract and present a summary for the user to confirm:

**Project identity:**
- Name
- One-sentence description
- Target deployment (web app, CLI, API, library, etc.)

**Tech stack** (infer from the spec, or ask if not specified):
- Language and framework
- Test runner and libraries
- Package manager
- Hosting / deployment target
- Key dependencies and external services

**Phases** (extract from the spec's roadmap/phases, or propose a phasing if the spec doesn't have one):
- Phase name and goal (one sentence each)
- Number of deliverables per phase
- Key dependencies between phases

**Wait for the user to confirm or adjust this summary before proceeding to file generation.**

### Step 2 — Generate docs/REQUIREMENTS.md

Write `docs/REQUIREMENTS.md` following this structure:

```markdown
# [Project Name] — Development Plan & Requirements

## Project Vision
[2-3 paragraphs synthesized from the spec's overview/purpose sections]

---

## Phase N — [Phase Name]

**Goal:** [One sentence from the spec or synthesized]

**Deliverables:**

1. [Specific, measurable deliverable]
2. [Another deliverable]

**Why this is Phase N:** [Dependencies and sequencing rationale]

---
[Repeat for all phases]

## Dependencies & Risk Notes
[Extract from spec or synthesize from phase analysis]
```

Rules:
- Deliverables must be specific and testable — "Scout agent with toolkit" not "build the scout functionality"
- Each deliverable should be completable in roughly 1-3 work sessions
- If a spec deliverable is too large, break it into sub-deliverables
- Include a validation/acceptance section per phase if the spec has one
- Preserve the spec's own phase structure if it has one — do not re-sequence unless the ordering has clear dependency violations

### Step 3 — Generate docs/ARCHITECTURE.md

Write `docs/ARCHITECTURE.md` following this structure:

```markdown
# [Project Name] — Technical Architecture

## System Overview
[Architecture diagram in ASCII/text or description of major components and data flow]

---

## Phase 1 — [Phase Name] Architecture

### [Component/Layer Name]
[Detailed architecture for this component]

### Key Architectural Decisions
- [Decision and rationale]

### Data Model
[If applicable — schemas, database structure, key types]

### Deployment
[Where and how Phase 1 components are deployed]

---

## Phase 2+ — Architecture Stubs
[1-2 sentence stub per remaining phase — expand when phase begins]
```

Rules:
- Phase 1 gets full architectural detail — enough for Claude Code to implement without guessing
- Include data models, directory structure, key interfaces/types, and configuration formats
- Extract technology choices from the spec (databases, frameworks, APIs)
- Later phases get stubs only — detailed architecture written too early becomes stale
- If the spec has architectural diagrams or component descriptions, preserve their substance

### Step 4 — Generate docs/PHASE_STATUS.md

Write `docs/PHASE_STATUS.md` by copying deliverables from the REQUIREMENTS.md you just generated:

```markdown
# Phase Status Tracker

> **Current Phase: 1 — [Phase Name]**
> Last updated: YYYY-MM-DD, session-YYYY-MM-DD-NNN

---

## Phase 1 — [Phase Name]

*Goal: [Copy from REQUIREMENTS.md]*

- ⬜ [Deliverable 1 — exact wording from REQUIREMENTS.md]
- ⬜ [Deliverable 2 — exact wording from REQUIREMENTS.md]

---
[Repeat for all phases]
```

Rules:
- Every deliverable line must be copied verbatim from REQUIREMENTS.md
- All items start as ⬜
- Do not add, remove, or reword any deliverables

### Step 5 — Generate CLAUDE.md

Read the template CLAUDE.md (this file is already in the workspace at `CLAUDE.md`) and fill in all placeholder sections:

- **Project Identity** — from Step 1 analysis
- **Tech Stack** — from Step 1 analysis
- **Current Phase** — set to Phase 1 with the correct name
- **Bootstrapping** — specify the exact tools/libraries to install during scaffolding, based on the tech stack
- **Directory Structure** — infer from the architecture, or use the spec's structure if specified
- **Coding Standards** — language-specific standards appropriate to the tech stack
- **Branching** — list all phase branch names derived from REQUIREMENTS.md
- **References** — add any project-specific reference files (spec doc, content guide, etc.)

Rules:
- Preserve all session workflow, testing, and git convention sections unchanged — these are universal
- Only fill in sections that have placeholder markers like `[PROJECT NAME]` or `[e.g., ...]`
- Add the original spec document to the References section
- If the spec references external services or APIs, note them in the Tech Stack

## After Generation

Present a summary of what was generated:

- **docs/REQUIREMENTS.md** — N phases, N total deliverables
- **docs/ARCHITECTURE.md** — Phase 1 detailed, N phases stubbed
- **docs/PHASE_STATUS.md** — N deliverables tracked
- **CLAUDE.md** — configured for [tech stack summary]

Suggest the user review each file, then:

```
git add docs/ CLAUDE.md
git commit -m "docs: scaffold project from spec"
git checkout -b phase/1-[phase-name]
```

Then they can start their first session with `/start-phase 1`.
