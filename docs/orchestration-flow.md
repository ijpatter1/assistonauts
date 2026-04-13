# Orchestration Flow — treasure-uat Expedition

> Generated from UAT workspace at `uat-workspace-phase5/`
> Build executed: 2026-04-13, 21:55–22:07 (12 minutes)
> Result: 26/35 missions completed, 3 failed, 6 blocked

---

## 1. Input

**Expedition config:** [`expeditions/treasure-uat/expedition.yaml`](../uat-workspace-phase5/expeditions/treasure-uat/expedition.yaml)

```yaml
expedition:
  name: treasure-uat
  scope:
    description: "A treasure hunt book with hidden clues, gemstones, and adventure guidance"
    keywords: [treasure, gems, clues, adventure, preparation]
  sources:
    local:
      - path: test-sources/
        pattern: "*.png" # 8 book page photographs
  scaling:
    budget:
      daily_token_limit: 200000
```

The user runs: `assistonauts build treasure-uat -w uat-workspace-phase5`

---

## 2. Orchestration Architecture

### Who does what

| Component               | Role                                                     | Makes LLM calls?              | Owns directories                |
| ----------------------- | -------------------------------------------------------- | ----------------------------- | ------------------------------- |
| **BuildOrchestrator**   | Sequences iterations, manages lifecycle, enforces budget | No (delegates to Captain)     | `expeditions/<name>/`           |
| **Captain** (agent)     | Plans missions, verifies compiled output                 | Yes — planning + verification | `expeditions/`, `station-logs/` |
| **Scout** (agent)       | Ingests raw sources (files, images)                      | Yes — vision model for images | `raw/`                          |
| **Compiler** (agent)    | Transforms raw sources into wiki articles                | Yes — compilation + summary   | `wiki/`                         |
| **Curator** (agent)     | Adds cross-references between articles                   | Yes — link classification     | `wiki/` (backlinks only)        |
| **Explorer** (agent)    | Answers queries against the knowledge base               | Yes — answer synthesis        | `wiki/explorations/`            |
| **Archivist** (service) | Indexes articles for search (FTS + vectors)              | No — deterministic            | `index/`                        |

### Key separation: Captain vs Compiler

The spec defines a clear boundary:

> "The Captain creates missions and sequences tasks; editorial decisions are delegated to Compiler plan mode."

In the current implementation:

- **Captain decides:** how many articles to compile, which sources to group, dependency ordering between missions, acceptance criteria for each mission, whether to include Explorer queries or Curator passes
- **Compiler decides:** article content, section structure, what to extract from sources, how to summarize
- **Captain verifies:** whether the Compiler's output meets the acceptance criteria (two-level completion)

**Where this gets blurry:** The Captain writes acceptance criteria like _"Lists all named gemstones"_ — that's an editorial judgment about what the article should contain. The spec says editorial decisions belong to the Compiler. In practice, the Captain is making editorial decisions through its criteria, and the Compiler is constrained to executing them. This worked well for 80%+ of missions but caused the recurring gemstones failure: the Captain demanded specific content the source material didn't support.

---

## 3. Iteration Flow

The orchestrator runs **named iteration phases** in a cycle:

```
Discovery → Structuring → Refinement → Structuring → Refinement → ...
                                        (repeat until no new work or max iterations)
```

Each iteration: Captain plans (LLM call) → Orchestrator executes missions → Results feed next iteration.

### Iteration 1: Discovery

**Goal:** Ingest all raw sources into `raw/articles/`.

```
Captain plans → 1 Scout mission
  mission-001: ingest 8 PNG files

Scout executes → 8 LLM calls (vision model, image → markdown)
  cover.png          → raw/articles/cover.md
  front-01-02.png    → raw/articles/front-01-02.md
  front-03-04.png    → raw/articles/front-03-04.md
  page-008-009.png   → raw/articles/page-008-009.md
  page-010-011.png   → raw/articles/page-010-011.md
  page-012-013.png   → raw/articles/page-012-013.md
  page-014-015.png   → raw/articles/page-014-015.md
  page-016-017.png   → raw/articles/page-016-017.md

Auto-approved (structural operation — no Captain verification)
```

**Artifacts:**

- 8 markdown files in [`raw/articles/`](../uat-workspace-phase5/raw/articles/)
- Mission YAML: [`missions/mission-001.yaml`](../uat-workspace-phase5/expeditions/treasure-uat/missions/mission-001.yaml)
- Trace: entries 0–10 in [`llm-trace.jsonl`](../uat-workspace-phase5/expeditions/treasure-uat/llm-trace.jsonl)

### Iteration 2: Structuring (first pass)

**Goal:** Captain reads raw articles, plans Compiler missions with dependency ordering.

```
Captain plans → 13 missions (LLM call reads raw article listing)
  6 compiler/compile_article (the articles to write)
  1 explorer/query (cross-cutting analysis)
  6 curator/cross_reference (link the compiled articles)

Dependencies: curator missions blocked on compiler + explorer completing first
```

**Execution:**

| Mission | Agent    | Type            | Title/Query                                                  | Result                    |
| ------- | -------- | --------------- | ------------------------------------------------------------ | ------------------------- |
| 002     | compiler | entity          | "The Treasure Hunt: Book Overview"                           | COMPLETED                 |
| 003     | compiler | concept         | "How the Treasure Hunt Works"                                | COMPLETED                 |
| 004     | compiler | exploration     | "Clues and Adventure Guidance: Pages 8-11"                   | COMPLETED                 |
| 005     | compiler | exploration     | "Clues and Adventure Guidance: Pages 12-15"                  | COMPLETED                 |
| 006     | compiler | exploration     | "Clues and Adventure Guidance: Pages 16-17"                  | COMPLETED                 |
| 007     | compiler | entity          | "Gemstones of the Treasure Hunt"                             | **FAILED** (3 rejections) |
| 008     | explorer | query           | "What are the key clues, hidden locations, and gemstones..." | **FAILED** (no archivist) |
| 009–014 | curator  | cross_reference | (various articles)                                           | **BLOCKED** by 007+008    |

**The gemstones failure (mission-007):** The Captain planned an entity article cataloguing specific gemstones. The Compiler produced a thematic overview instead. The Captain rejected it 3 times with escalating specificity:

1. _"output contains ZERO gemstone content despite article being titled 'Gemstones'"_
2. _"rejection stands... it is zero coverage of any named gemstone"_
3. _"assessment remains unchanged... not a matter of partial coverage"_

The rejected article was cleaned up (deleted from `wiki/`). The 6 curator missions that depended on it remained blocked.

**The explorer failure (mission-008):** The Explorer agent lacked an Archivist/EmbeddingClient for retrieval, so it returned `success=False` immediately. (Fixed in commit `568c25a` — same root cause as the earlier curator bug.)

**Artifacts:**

- 5 wiki articles in [`wiki/`](../uat-workspace-phase5/wiki/)
- Mission YAMLs: [`missions/mission-002.yaml`](../uat-workspace-phase5/expeditions/treasure-uat/missions/mission-002.yaml) through `mission-014.yaml`

### Indexing Step (between Structuring and Refinement)

```
Orchestrator → Archivist indexes 5 compiled wiki articles
  FTS5 (keyword search) + metadata stored in index/assistonauts.db
  No LLM calls — deterministic indexing
```

This step was added to fix a bug where the Curator's multi-pass retriever had an empty index. Without it, cross-referencing is a no-op.

### Iteration 3: Refinement (first pass)

**Goal:** Curator cross-references all compiled articles.

```
Captain plans → 5 curator missions (remapped from blocked 009-014)
  mission-009-r1: cross-reference "how-the-treasure-hunt-works"
  mission-010-r1: cross-reference "the-treasure-hunt-book-overview"
  mission-011-r1: cross-reference "clues-and-adventure-guidance-pages-811"
  mission-012-r1: cross-reference "clues-and-adventure-guidance-pages-1215"
  mission-013-r1: cross-reference "clues-and-adventure-guidance-pages-1617"

All auto-approved (structural operation)
```

Each curator mission: retrieve related articles via multi-pass → LLM classifies STRONG/WEAK → write backlinks.

**Artifacts:**

- Modified wiki articles (See Also sections added)
- Cross-reference log: [`.assistonauts/curator/cross-references.jsonl`](../uat-workspace-phase5/.assistonauts/curator/cross-references.jsonl)

### Iteration 4: Structuring (second pass)

**Goal:** Captain reads updated summaries, identifies articles still needed.

```
Captain plans → 7 missions
  4 compiler (new articles the first pass didn't cover)
  1 explorer (another query attempt)
  2 curator (link the new articles)
```

| Mission | Agent    | Type            | Title/Query                                    | Result     |
| ------- | -------- | --------------- | ---------------------------------------------- | ---------- |
| 014-r1  | compiler | entity          | "Front Matter and Publication Details"         | COMPLETED  |
| 015     | compiler | concept         | "The Five Treasure Boxes"                      | COMPLETED  |
| 016     | compiler | entity          | "The Treasure Chest Contents"                  | COMPLETED  |
| 017     | compiler | exploration     | "Historical Figures Named in the Introduction" | COMPLETED  |
| 018     | explorer | query           | "What preparation advice does the book give?"  | **FAILED** |
| 019     | curator  | cross_reference | book overview article                          | COMPLETED  |
| 020     | curator  | cross_reference | how hunt works article                         | COMPLETED  |

### Iteration 5: Refinement (second pass)

**Goal:** Comprehensive cross-referencing of the full 9-article corpus.

```
Captain plans → 9 curator missions (one per article)
  All completed, all auto-approved
  Added cross-references between new articles (treasure boxes,
  chest contents, historical figures) and existing articles
```

**Final state:** 9/9 articles cross-referenced (100%).

---

## 4. Verification Flow

For **compiler** missions, two-level completion applies:

```
Compiler writes article to disk
  ↓
Orchestrator calls Captain for verification (up to 3 attempts)
  ↓
Captain reads article content (first 80 lines) + acceptance criteria
  ↓
VERIFIED → mission completes, article stays
REJECTED → feedback loop:
  Captain's rejection reason fed back as conversation context
  "Reconsider — the agent worked from limited source material..."
  ↓
  Still REJECTED after 3 attempts → article deleted, mission fails
```

For **curator** and **scout** missions: auto-approved (structural operations where the agent's own validation is sufficient).

For **explorer** missions: would go through verification, but both failed before producing output.

---

## 5. Mission ID Deduplication

The Captain reuses mission IDs across iterations (e.g., `mission-001` in both Discovery and a later Structuring plan). The orchestrator detects collisions and remaps:

```
mission-009 (Structuring, blocked) → kept as mission-009
mission-009 (Refinement, new plan) → remapped to mission-009-r1
mission-001 (Budget test, iter 2)  → remapped to mission-001-r1
mission-001 (Budget test, iter 4)  → remapped to mission-001-r2
```

Without dedup, `INSERT OR REPLACE` in the ledger would silently overwrite earlier missions.

---

## 6. Token Budget

| Agent     | Tokens      | % of Total                   |
| --------- | ----------- | ---------------------------- |
| Compiler  | 49,014      | 38.5%                        |
| Captain   | 41,676      | 32.7%                        |
| Scout     | 19,372      | 15.2%                        |
| Curator   | 17,235      | 13.5%                        |
| Explorer  | 0           | 0% (failed before execution) |
| **Total** | **127,297** | **63.6% of 200K budget**     |

Captain is the second-largest token consumer — planning (5 calls) + verification (10+ calls including retries) is expensive. The 3-attempt verification loop for the gemstones rejection alone cost ~3 verification calls.

---

## 7. Artifact Map

All artifacts from this build, relative to `uat-workspace-phase5/`:

```
expeditions/treasure-uat/
  expedition.yaml          — input config
  plan.yaml                — Captain's full plan across all iterations
  build-report.md          — human-readable build summary
  llm-trace.jsonl          — complete LLM I/O trace (116 entries)
  ledger.db                — mission state (SQLite, source of truth)
  budget.db                — token usage tracking
  missions/
    mission-001.yaml       — through mission-029-r2.yaml (35 files)

raw/articles/
  cover.md                 — through page-016-017.md (8 files)

wiki/
  entity/
    the-treasure-hunt-book-overview.md
    front-matter-and-publication-details.md
    the-treasure-chest-contents.md
  concept/
    how-the-treasure-hunt-works.md
    the-five-treasure-boxes.md
  exploration/
    clues-and-adventure-guidance-pages-811.md
    clues-and-adventure-guidance-pages-1215.md
    clues-and-adventure-guidance-pages-1617.md
    historical-figures-named-in-the-treasure-hunt-introduction.md

index/
  assistonauts.db          — FTS5 + vector index
  manifest.json            — content hash tracking

.assistonauts/
  logs/
    captain.jsonl           — structured log (verification conversations)
    compiler.jsonl
    curator.jsonl
    scout.jsonl
  curator/
    cross-references.jsonl  — curator decision audit trail
  tasks/
    task-mission-*.yaml     — task-level audit trails
```

---

## 8. Role Separation: Spec vs Implementation

### What the spec says

> "The Captain creates missions (multi-step objectives) and sequences tasks within them. Editorial decisions (article types, groupings, titles) are delegated to the Compiler's plan mode — the Captain orchestrates when and how plans are executed."

### What actually happens

| Decision                                      | Spec says          | Implementation does                          |
| --------------------------------------------- | ------------------ | -------------------------------------------- |
| How many articles to compile                  | Compiler plan mode | **Captain** (via Structuring LLM call)       |
| Which sources to group                        | Compiler plan mode | **Captain** (in mission inputs.sources)      |
| Article type (concept/entity/log/exploration) | Compiler plan mode | **Captain** (in mission inputs.article_type) |
| Article title                                 | Compiler plan mode | **Captain** (in mission inputs.title)        |
| Acceptance criteria                           | Captain            | Captain                                      |
| Dependency ordering                           | Captain            | Captain                                      |
| Article content                               | Compiler           | Compiler                                     |
| Whether to include Explorer queries           | Captain            | Captain                                      |
| When to run Curator passes                    | Captain            | Captain                                      |
| Cross-reference link classification           | Curator            | Curator                                      |

### The gap

The Compiler has a `plan()` method that analyzes raw sources and proposes article groupings, types, and titles. This is the "Compiler plan mode" from the spec. But the orchestrator's Structuring iteration **bypasses Compiler plan mode entirely** — the Captain's planning LLM call directly decides article groupings, types, and titles.

This means:

1. The Captain makes editorial decisions it shouldn't (per spec)
2. The Compiler plan mode exists but is unused during orchestrated builds
3. Acceptance criteria written by the Captain sometimes mismatch what the source material can support (the gemstones problem)

### Possible resolution

The Structuring iteration could be split:

1. **Captain** decides which raw sources need compilation (scope decision)
2. **Compiler plan mode** proposes how to compile them (editorial decision)
3. **Captain** reviews and sequences the Compiler's plan (orchestration decision)

This would align the implementation with the spec and likely reduce the gemstones-type failures, since the Compiler would be proposing articles based on what it sees in the source material rather than what the Captain imagines should be there.
