# Requirements: omni-ai-agents

**Defined:** 2026-02-12
**Updated:** 2026-02-14 (v1.2 requirements merged, traceability updated)
**Core Value:** Computational double programming for regulated biostatistics

## v1.1 Requirements

### Stderr Filtering

- [x] **STDERR-01**: Strip R package loading messages (library load, attach, mask warnings, tidyverse conflicts) from stderr before processing
- [x] **STDERR-02**: Preserve actual R errors and warnings in filtered stderr output
- [x] **STDERR-03**: Apply stderr filtering before error classification, LLM retry feedback, and error display

### Error Classification

- [x] **ERRCLASS-01**: Fix `"object"` pattern in `classify_error` to not false-match on `"The following object is masked"`
- [x] **ERRCLASS-02**: Audit all `code_patterns` for similar false-positive risks with standard R stderr noise
- [x] **ERRCLASS-03**: Make error patterns match in error-context only (e.g., lines starting with `Error` or within error messages)

### Error Display

- [x] **ERRDSP-01**: Show actual R error in terminal error panel and pipeline logs, not truncated package loading noise
- [x] **ERRDSP-02**: Ensure the 500-char truncation window contains the real error by filtering noise before truncation

## v1.2 Requirements

### Protocol Parser

- [ ] **PARSE-01**: User can provide a .docx protocol document and receive a structured config.yaml
- [ ] **PARSE-02**: Parser extracts trial parameters (n_subjects, randomization_ratio, baseline values, etc.) into TrialConfig format
- [ ] **PARSE-03**: Parser validates extracted values against Pydantic model bounds and types
- [ ] **PARSE-04**: Parser displays all extracted values for user confirmation before writing config
- [ ] **PARSE-05**: New `parse-protocol` CLI subcommand accepts .docx input path and config output path

### CSR Data Dictionary

- [ ] **DICT-01**: Data dictionary section removed from CSR Word document template
- [ ] **DICT-02**: SDTM data_dictionary.csv generated in sdtm/ output directory with columns: Variable, Label, Type, Derivation
- [ ] **DICT-03**: ADaM data_dictionary.csv generated in adam/ output directory with columns: Variable, Label, Type, Derivation
- [ ] **DICT-04**: Data dictionaries generated deterministically by orchestrator (no LLM call)
- [ ] **DICT-05**: Schema validator checks for data_dictionary.csv presence in output directories

### Interactive Mode

- [ ] **INTER-01**: `--interactive` CLI flag enables stage-level pause mode
- [ ] **INTER-02**: Pipeline pauses after each logical stage (simulator, parallel analysis, comparison, resolution, reporting)
- [ ] **INTER-03**: Rich Panel summary displayed at each pause point showing step name, metrics, output files, and validation status
- [ ] **INTER-04**: User presses Enter to continue or Ctrl+C to abort at each pause
- [ ] **INTER-05**: Interactive input handled via asyncio run_in_executor (non-blocking event loop)
- [ ] **INTER-06**: Rich Live display properly stops and restarts around interactive pause points

## v2 Requirements

### Protocol Parser Enhancements

- **PARSE-V2-01**: Source quoting — show which part of the document each parameter came from
- **PARSE-V2-02**: Interactive Q&A mode for ambiguous parameters

### Interactive Mode Enhancements

- **INTER-V2-01**: Step-level pauses within parallel tracks (finer granularity)
- **INTER-V2-02**: Step selection (`--steps sdtm,adam`) for partial pipeline runs

### Pipeline Resilience (carried from v1.1)

- **RESIL-01**: Catch per-track exceptions in asyncio.gather() so one track failure does not crash the other
- **RESIL-02**: If one track fails, continue pipeline with the surviving track's results
- **RESIL-03**: Display failed track status in pipeline display (step marked as failed, progress bar updated)
- **RESIL-04**: Degrade gracefully to single-track mode: skip stage comparison, proceed to Medical Writer with surviving track

## Out of Scope

| Feature | Reason |
|---------|--------|
| Define-XML generation | Disproportionate complexity for simulation pipeline |
| Dual-LLM protocol parsing | Protocol parsing is deterministic extraction, not adversarial |
| Protocol parser that edits config.yaml in-place | Risk of corrupting user comments/formatting |
| Auto-detection of protocol file format (.pdf, .txt, .rtf) | Support .docx only (industry standard) |
| Interactive mode with rollback | Requires checkpoint/restore infrastructure |
| Data dictionary in JSON format | CSV is consistent with data file format |
| Smarter `_pick_best_track` heuristic | Deferred to v2.0 — not related to usability |
| Schema validator integration in resolution hints | Deferred to v2.0 |
| Suppressing R package loading at Docker/Rscript level | Filtering in Python is safer and more maintainable |

## Traceability

Which phases cover which requirements. Updated by create-roadmap.

| Requirement | Phase | Status |
|-------------|-------|--------|
| STDERR-01 | Phase 3 (v1.1) | Complete |
| STDERR-02 | Phase 3 (v1.1) | Complete |
| STDERR-03 | Phase 3 (v1.1) | Complete |
| ERRCLASS-01 | Phase 3 (v1.1) | Complete |
| ERRCLASS-02 | Phase 3 (v1.1) | Complete |
| ERRCLASS-03 | Phase 3 (v1.1) | Complete |
| ERRDSP-01 | Phase 3 (v1.1) | Complete |
| ERRDSP-02 | Phase 3 (v1.1) | Complete |
| DICT-01 | Phase 5 | Pending |
| DICT-02 | Phase 5 | Pending |
| DICT-03 | Phase 5 | Pending |
| DICT-04 | Phase 5 | Pending |
| DICT-05 | Phase 5 | Pending |
| INTER-01 | Phase 6 | Pending |
| INTER-02 | Phase 6 | Pending |
| INTER-03 | Phase 6 | Pending |
| INTER-04 | Phase 6 | Pending |
| INTER-05 | Phase 6 | Pending |
| INTER-06 | Phase 6 | Pending |
| PARSE-01 | Phase 7 | Pending |
| PARSE-02 | Phase 7 | Pending |
| PARSE-03 | Phase 7 | Pending |
| PARSE-04 | Phase 7 | Pending |
| PARSE-05 | Phase 7 | Pending |

**Coverage:**
- v1.1 requirements: 8 complete
- v1.2 requirements: 16 pending (all mapped)
- Total v1 requirements: 24
- Mapped to phases: 24
- Unmapped: 0

---
*Requirements defined: 2026-02-12*
*Last updated: 2026-02-14 after v1.2 roadmap creation*
