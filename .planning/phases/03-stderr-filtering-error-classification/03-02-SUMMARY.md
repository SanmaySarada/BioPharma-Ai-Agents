---
phase: 03-stderr-filtering-error-classification
plan: 02
subsystem: pipeline
tags: [regex, stderr, R, error-classification, retry, integration]

# Dependency graph
requires:
  - phase: 03-01
    provides: "filter_r_stderr() function that strips R package loading noise from stderr"
provides:
  - "Context-aware classify_error() with regex patterns (no false positives on 'object is masked')"
  - "filter_r_stderr wired into execute_with_retry at single chokepoint before all 7+ stderr consumers"
  - "filter_r_stderr exported from pipeline __init__.py"
  - "13 tests covering classify_error fixes and end-to-end filter+classify integration"
affects:
  - "All downstream pipeline consumers: logging, orchestrator, display, LLM feedback"
  - "Phase 4 (if any further error classification work)"

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Module-level compiled regex list (_CODE_BUG_REGEX) for context-sensitive error classification"
    - "Single chokepoint filtering: replace DockerResult with filtered copy before any consumption"

key-files:
  created:
    - "tests/test_pipeline/test_retry.py"
  modified:
    - "src/omni_agents/pipeline/retry.py"
    - "src/omni_agents/pipeline/__init__.py"

key-decisions:
  - "Split code_patterns into _CODE_BUG_REGEX (compiled, module-level) and _CODE_BUG_SUBSTRINGS (safe substring list) -- avoids recompilation per call while keeping clear separation of pattern types"
  - "Regex patterns search against raw stderr (not lowercased) because they use re.IGNORECASE or are intentionally case-sensitive (^Error in)"

patterns-established:
  - "Immutable Pydantic model update: create new DockerResult with filtered stderr rather than mutating"
  - "Regex for context-sensitive classification, substrings for unambiguous patterns"

# Metrics
duration: 3min
completed: 2026-02-12
---

# Phase 3 Plan 02: Filter Integration & classify_error Fix Summary

**Context-aware classify_error regex patterns wired with filter_r_stderr at single execute_with_retry chokepoint, eliminating false positives on R package noise**

## Performance

- **Duration:** 3 min
- **Started:** 2026-02-12T23:34:44Z
- **Completed:** 2026-02-12T23:37:48Z
- **Tasks:** 2
- **Files modified:** 3

## Accomplishments
- Replaced dangerous substring matches ("object", "error in", "unexpected") with context-aware regex patterns that match "object 'x' not found" but NOT "object is masked" (ERRCLASS-01 fixed)
- Wired filter_r_stderr() into execute_with_retry() at single chokepoint after Docker execution, so all 7+ downstream stderr consumers receive filtered output (STDERR-03 satisfied)
- Created 13 tests: 10 classify_error unit tests covering all error classifications + 3 end-to-end integration tests proving filter+classify correctness on realistic survminer/tidyverse stderr
- Full test suite: 114 tests passing, zero regressions, mypy --strict clean

## Task Commits

Each task was committed atomically:

1. **Task 1: Fix classify_error patterns and wire filter into execute_with_retry** - `5421048` (feat)
2. **Task 2: Add integration tests for classify_error fixes and filtered retry flow** - `5d99df3` (test)

## Files Created/Modified
- `src/omni_agents/pipeline/retry.py` - Fixed classify_error with _CODE_BUG_REGEX and _CODE_BUG_SUBSTRINGS; wired filter_r_stderr into execute_with_retry; added `import re` and filter import
- `src/omni_agents/pipeline/__init__.py` - Added filter_r_stderr to imports and __all__ exports
- `tests/test_pipeline/test_retry.py` - 13 tests (196 lines): classify_error unit tests + filter+classify integration tests

## Decisions Made
- Split code patterns into two lists: `_CODE_BUG_REGEX` (4 compiled regex patterns at module level) and `_CODE_BUG_SUBSTRINGS` (8 safe substring patterns) -- regex patterns handle context-sensitive matching (word boundaries, line anchors) while substrings handle unambiguous patterns
- Regex patterns search against raw stderr (not lowercased) because each regex uses `re.IGNORECASE` where needed or is intentionally case-sensitive (`^Error in ` matches R's exact capitalization)

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

None.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness
- Phase 3 complete: both filter_r_stderr (Plan 01) and its integration with classify_error/execute_with_retry (Plan 02) are shipped
- 114 tests total, all passing, mypy --strict clean across both modules
- All 7+ stderr consumption points in the pipeline now receive filtered stderr automatically
- The _CODE_BUG_REGEX list is easily extensible if new R error patterns emerge

---
*Phase: 03-stderr-filtering-error-classification*
*Completed: 2026-02-12*
