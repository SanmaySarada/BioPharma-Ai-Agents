---
phase: 03-stderr-filtering-error-classification
plan: 01
subsystem: pipeline
tags: [regex, stderr, R, filtering, tidyverse, survminer]

# Dependency graph
requires: []
provides:
  - "filter_r_stderr() function that strips R package loading noise from stderr"
  - "_NOISE_PATTERNS tuple with 13 compiled regex patterns for R noise"
  - "13 pytest test cases covering all noise pattern categories"
affects:
  - "03-02 (wiring filter into execute_with_retry)"
  - "03-03 (error classification pattern tightening)"

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Line-based regex filtering with safety-net passthrough for Error lines"
    - "Module-level compiled regex tuple for pattern matching"

key-files:
  created:
    - "src/omni_agents/pipeline/stderr_filter.py"
    - "tests/test_pipeline/test_stderr_filter.py"
  modified: []

key-decisions:
  - "Used 2-space indent threshold for continuation lines (^\s{2,}) instead of 4-space -- catches both dplyr indented object names and Registered S3 method table rows"
  - "Empty string return for empty/falsy input (not the original input) -- consistent behavior"

patterns-established:
  - "Safety-net pattern: lines starting with Error/error are never filtered regardless of content"
  - "Noise patterns as module-level compiled tuple for single-compile efficiency"

# Metrics
duration: 3min
completed: 2026-02-12
---

# Phase 3 Plan 01: Stderr Filter Core Summary

**filter_r_stderr() with 13 regex noise patterns, TDD-verified against real tidyverse/survminer/dplyr stderr samples**

## Performance

- **Duration:** 3 min
- **Started:** 2026-02-12T23:29:27Z
- **Completed:** 2026-02-12T23:32:55Z
- **Tasks:** 2
- **Files modified:** 2

## Accomplishments
- TDD RED-GREEN cycle producing filter_r_stderr() with 13 compiled regex noise patterns
- Comprehensive test coverage with real R stderr samples (tidyverse 2.0 Unicode banner, survminer loading, dplyr masking, Registered S3 method)
- Safety net ensuring Error/error lines are never filtered, even when containing noise-like words
- Legitimate R warnings (NAs introduced, NaNs produced) preserved correctly
- mypy --strict clean, full test suite (101 tests) passes with no regressions

## Task Commits

Each task was committed atomically:

1. **Task 1: RED -- Write failing tests for filter_r_stderr** - `50ba15d` (test)
2. **Task 2: GREEN -- Implement filter_r_stderr to pass all tests** - `60724f9` (feat)

_TDD plan: 2 commits (test -> feat). No refactor needed -- implementation was clean on first pass._

## Files Created/Modified
- `src/omni_agents/pipeline/stderr_filter.py` - filter_r_stderr() function and _NOISE_PATTERNS compiled regex tuple
- `tests/test_pipeline/test_stderr_filter.py` - 13 test cases with real R stderr samples as module-level constants

## Decisions Made
- Used `^\s{2,}` (2-space threshold) instead of `^\s{4,}` (4-space) for indented continuation lines -- the Registered S3 method table uses 2-space indentation (`  method      from`), so 4-space threshold would miss those lines
- Return empty string `""` for empty/falsy input rather than returning the original input value -- consistent with the function's contract of returning filtered output

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

None.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness
- filter_r_stderr() is ready to be wired into execute_with_retry() in Plan 02
- The _NOISE_PATTERNS tuple is easily extensible if new R packages produce noise
- classify_error() pattern tightening (Plan 03) can proceed independently

---
*Phase: 03-stderr-filtering-error-classification*
*Completed: 2026-02-12*
