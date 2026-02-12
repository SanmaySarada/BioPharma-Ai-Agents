# Requirements: omni-ai-agents v1.1

**Defined:** 2026-02-12
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

### Pipeline Resilience

- [ ] **RESIL-01**: Catch per-track exceptions in `asyncio.gather()` so one track failure does not crash the other
- [ ] **RESIL-02**: If one track fails, continue pipeline with the surviving track's results
- [ ] **RESIL-03**: Display failed track status in pipeline display (step marked as failed, progress bar updated)
- [ ] **RESIL-04**: Degrade gracefully to single-track mode: skip stage comparison, proceed to Medical Writer with surviving track

## v2 Requirements

None deferred from v1.1.

## Out of Scope

| Feature | Reason |
|---------|--------|
| Smarter `_pick_best_track` heuristic | Deferred to v2.0 — not related to reliability |
| Schema validator integration in resolution hints | Deferred to v2.0 — not related to reliability |
| Suppressing R package loading at Docker/Rscript level | Would change Docker execution contract; filtering in Python is safer and more maintainable |

## Traceability

Which phases cover which requirements. Updated by create-roadmap.

| Requirement | Phase | Status |
|-------------|-------|--------|
| STDERR-01 | Phase 3 | Complete |
| STDERR-02 | Phase 3 | Complete |
| STDERR-03 | Phase 3 | Complete |
| ERRCLASS-01 | Phase 3 | Complete |
| ERRCLASS-02 | Phase 3 | Complete |
| ERRCLASS-03 | Phase 3 | Complete |
| ERRDSP-01 | Phase 3 | Complete |
| ERRDSP-02 | Phase 3 | Complete |
| RESIL-01 | Phase 4 | Pending |
| RESIL-02 | Phase 4 | Pending |
| RESIL-03 | Phase 4 | Pending |
| RESIL-04 | Phase 4 | Pending |

**Coverage:**
- v1.1 requirements: 12 total
- Mapped to phases: 12
- Unmapped: 0 ✓

---
*Requirements defined: 2026-02-12*
*Last updated: 2026-02-12 after Phase 3 completion*
