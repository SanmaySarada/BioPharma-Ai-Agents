# Roadmap: omni-ai-agents

## Milestones

- ✅ **v1.0 Symmetric Double Programming** — Phases 1-2 (shipped 2026-02-12)
- ✅ **v1.1 Pipeline Reliability** — Phase 3 (shipped 2026-02-12)
- 🚧 **v1.2 Usability & Flexibility** — Phases 5-7 (in progress)

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
**Plans**: 1 plan

Plans:
- [x] 02-01: Display layer update

</details>

<details>
<summary>✅ v1.1 Pipeline Reliability (Phase 3) — SHIPPED 2026-02-12</summary>

### Phase 3: Stderr Filtering & Error Classification
**Goal**: Real R errors are visible, correctly classified, and fed back to the LLM for effective retries
**Depends on**: Phase 2 (v1.0 complete)
**Requirements**: STDERR-01, STDERR-02, STDERR-03, ERRCLASS-01, ERRCLASS-02, ERRCLASS-03, ERRDSP-01, ERRDSP-02
**Success Criteria** (what must be TRUE):
  1. When an R script fails, the actual R error is visible in the terminal error panel (not package loading noise)
  2. `classify_error` correctly classifies errors from scripts that load survminer/tidyverse (no false positives on "object is masked")
  3. LLM retry attempts receive filtered stderr with the actual error, enabling effective code fixes
**Plans**: 2 plans

Plans:
- [x] 03-01: TDD: filter_r_stderr() function with comprehensive tests
- [x] 03-02: Integrate filter into retry chokepoint + fix classify_error patterns

</details>

### 🚧 v1.2 Usability & Flexibility (In Progress)

**Milestone Goal:** Make the pipeline configurable from a natural-language protocol document, clean up the CSR output, and add an interactive execution mode for step-by-step review.

- [ ] **Phase 5: CSR Data Dictionary Extraction** — Move data dictionary from CSR to standalone CSV files
- [ ] **Phase 6: Interactive Execution Mode** — Stage-level pause mode for step-by-step pipeline review
- [ ] **Phase 7: Protocol Parser Agent** — Natural-language .docx to structured trial config

## Phase Details

### Phase 5: CSR Data Dictionary Extraction
**Goal**: Data dictionary metadata lives alongside data files, not embedded in the CSR
**Depends on**: Phase 3 (v1.1 complete — medical writer template exists)
**Requirements**: DICT-01, DICT-02, DICT-03, DICT-04, DICT-05
**Success Criteria** (what must be TRUE):
  1. CSR Word document no longer contains a data dictionary section
  2. `sdtm/data_dictionary.csv` exists alongside SDTM data files with variable definitions
  3. `adam/data_dictionary.csv` exists alongside ADaM data files with variable definitions
  4. Schema validator confirms data dictionary files are present in output
**Research**: Unlikely (standard patterns, no LLM needed)
**Plans**: TBD

Plans:
- [ ] 05-01: TBD

### Phase 6: Interactive Execution Mode
**Goal**: Users can review pipeline output step-by-step before each stage proceeds
**Depends on**: Phase 5
**Requirements**: INTER-01, INTER-02, INTER-03, INTER-04, INTER-05, INTER-06
**Success Criteria** (what must be TRUE):
  1. User can run pipeline with `--interactive` flag to enable pause mode
  2. Pipeline pauses after each logical stage and displays a summary panel with metrics and file paths
  3. User presses Enter to continue or Ctrl+C to abort at each pause
  4. Rich Live display remains functional after pausing and resuming
**Research**: Unlikely (Rich Live stop/start proven in codebase, asyncio patterns well-documented)
**Plans**: TBD

Plans:
- [ ] 06-01: TBD

### Phase 7: Protocol Parser Agent
**Goal**: Users can generate pipeline config from a natural-language protocol document
**Depends on**: Phase 5
**Requirements**: PARSE-01, PARSE-02, PARSE-03, PARSE-04, PARSE-05
**Success Criteria** (what must be TRUE):
  1. User can run `parse-protocol protocol.docx -o config.yaml` to generate config
  2. Parser extracts all TrialConfig fields from natural-language prose
  3. Extracted values are validated against Pydantic bounds before writing
  4. User sees all extracted values for confirmation before config is written
**Research**: Likely (prompt engineering for numeric extraction, LLM accuracy concerns)
**Plans**: TBD

Plans:
- [ ] 07-01: TBD

## Progress

**Execution Order:**
Phases execute in numeric order: 5 → 6 → 7

| Phase | Milestone | Plans Complete | Status | Completed |
|-------|-----------|----------------|--------|-----------|
| 1. Symmetric Double Programming | v1.0 | 3/3 | Complete | 2026-02-12 |
| 2. Display Layer Update | v1.0 | 1/1 | Complete | 2026-02-12 |
| 3. Stderr Filtering & Error Classification | v1.1 | 2/2 | Complete | 2026-02-12 |
| 5. CSR Data Dictionary Extraction | v1.2 | 0/? | Not started | - |
| 6. Interactive Execution Mode | v1.2 | 0/? | Not started | - |
| 7. Protocol Parser Agent | v1.2 | 0/? | Not started | - |
