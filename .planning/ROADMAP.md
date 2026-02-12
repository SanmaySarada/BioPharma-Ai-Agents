# Roadmap: omni-ai-agents

## Milestones

- ✅ **v1.0 Symmetric Double Programming** — Phases 1-2 (shipped 2026-02-12)
- 🚧 **v1.1 Pipeline Reliability** — Phases 3-4 (in progress)

## Phases

<details>
<summary>✅ v1.0 Symmetric Double Programming (Phases 1-2) — SHIPPED 2026-02-12</summary>

### Phase 1: Symmetric Double Programming
**Goal**: Generic `_run_track()` for both LLM tracks with stage comparison and resolution
**Plans**: 3 plans

Plans:
- [x] 01-01: Orchestrator refactor
- [x] 01-02: Stage comparator
- [x] 01-03: Resolution loop

### Phase 2: Display Layer Update
**Goal**: Pipeline display showing all 9 track-qualified steps with resolution callbacks
**Plans**: 2 plans

Plans:
- [x] 02-01: Display layer update

</details>

### 🚧 v1.1 Pipeline Reliability (In Progress)

**Milestone Goal:** Fix error handling so the pipeline reliably completes even when one track's R code fails, and make R errors visible for effective debugging and retry.

- [ ] **Phase 3: Stderr Filtering & Error Classification** — Fix error visibility, classification, and retry feedback
- [ ] **Phase 4: Pipeline Resilience** — Per-track error isolation with single-track fallback

## Phase Details

### Phase 3: Stderr Filtering & Error Classification
**Goal**: Real R errors are visible, correctly classified, and fed back to the LLM for effective retries
**Depends on**: Phase 2 (v1.0 complete)
**Requirements**: STDERR-01, STDERR-02, STDERR-03, ERRCLASS-01, ERRCLASS-02, ERRCLASS-03, ERRDSP-01, ERRDSP-02
**Success Criteria** (what must be TRUE):
  1. When an R script fails, the actual R error is visible in the terminal error panel (not package loading noise)
  2. `classify_error` correctly classifies errors from scripts that load survminer/tidyverse (no false positives on "object is masked")
  3. LLM retry attempts receive filtered stderr with the actual error, enabling effective code fixes
**Research**: Unlikely (known codebase, clear fix)
**Plans**: TBD

Plans:
- [ ] 03-01: TBD

### Phase 4: Pipeline Resilience
**Goal**: One track failure does not crash the pipeline; surviving track continues to produce results
**Depends on**: Phase 3
**Requirements**: RESIL-01, RESIL-02, RESIL-03, RESIL-04
**Success Criteria** (what must be TRUE):
  1. When one track fails, the other track continues to completion
  2. Pipeline produces a Clinical Study Report from the surviving track's results
  3. Failed track shows error status in the pipeline display
  4. Stage comparison is skipped when only one track succeeds
**Research**: Unlikely (asyncio patterns well understood)
**Plans**: TBD

Plans:
- [ ] 04-01: TBD

## Progress

| Phase | Milestone | Plans Complete | Status | Completed |
|-------|-----------|----------------|--------|-----------|
| 1. Symmetric Double Programming | v1.0 | 3/3 | Complete | 2026-02-12 |
| 2. Display Layer Update | v1.0 | 1/1 | Complete | 2026-02-12 |
| 3. Stderr Filtering & Error Classification | v1.1 | 0/? | Not started | - |
| 4. Pipeline Resilience | v1.1 | 0/? | Not started | - |
