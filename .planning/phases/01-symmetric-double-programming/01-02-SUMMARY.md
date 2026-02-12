---
phase: 01-symmetric-double-programming
plan: 02
subsystem: pipeline
tags: [comparison, sdtm, adam, stats, tolerance, pydantic, csv, json]

# Dependency graph
requires:
  - phase: 01-01
    provides: "StageComparison, StageComparisonResult, TrackResult models in resolution.py"
provides:
  - "StageComparator class with compare_sdtm, compare_adam, compare_stats, compare_all_stages"
  - "STATS_TOLERANCES dict matching ConsensusJudge tolerance values"
  - "12 unit tests covering match, mismatch, tolerance boundary cases"
affects: [01-03, 01-04]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Classmethod-only comparator pattern (no instance state) matching SchemaValidator style"
    - "Locally defined tolerances to avoid coupling between StageComparator and ConsensusJudge"

key-files:
  created:
    - "src/omni_agents/pipeline/stage_comparator.py"
    - "tests/test_pipeline/test_stage_comparator.py"
  modified: []

key-decisions:
  - "STATS_TOLERANCES defined locally in stage_comparator.py rather than imported from ConsensusJudge to avoid coupling"
  - "All comparison methods are classmethods following SchemaValidator pattern"

patterns-established:
  - "Stage comparison returns StageComparison model with matches bool, issues list, and per-track summary dicts"
  - "Test helpers (_make_dm_rows, _make_vs_rows, _make_adam_summary, _make_stats_results) for generating fixture data"

# Metrics
duration: 3min
completed: 2026-02-12
---

# Phase 1 Plan 2: StageComparator Summary

**Per-stage comparison of Track A/B outputs: SDTM (row counts, columns, distributions), ADaM (n_rows/events/censored/PARAMCD), Stats (toleranced metric comparison matching ConsensusJudge thresholds)**

## Performance

- **Duration:** 3 min
- **Started:** 2026-02-12T08:38:29Z
- **Completed:** 2026-02-12T08:41:41Z
- **Tasks:** 2
- **Files created:** 2

## Accomplishments
- StageComparator class with all four comparison classmethods covering SDTM, ADaM, and Stats stages
- Tolerance-based stats comparison using ConsensusJudge-compatible thresholds (logrank_p abs 1e-3, cox_hr rel 0.1%, km_median abs 0.5)
- 12 comprehensive unit tests covering identical match, mismatch detection, and tolerance boundary cases
- Full test suite (68 tests) passes with zero regressions

## Task Commits

Each task was committed atomically:

1. **Task 1: Create StageComparator class** - `1cc2993` (feat)
2. **Task 2: Write StageComparator unit tests** - `806dbc5` (test)

**Plan metadata:** `f598cf2` (docs: complete plan)

## Files Created/Modified
- `src/omni_agents/pipeline/stage_comparator.py` - StageComparator class with compare_sdtm, compare_adam, compare_stats, compare_all_stages classmethods
- `tests/test_pipeline/test_stage_comparator.py` - 12 unit tests covering all comparison methods with fixture helpers

## Decisions Made
- STATS_TOLERANCES defined locally in stage_comparator.py rather than imported from ConsensusJudge -- avoids coupling between the two modules while keeping tolerance values identical
- Followed classmethod-only pattern from SchemaValidator (no instance state needed)
- Both tracks use identical results.json format (table2, table3, metadata keys) since both run the full pipeline in symmetric architecture

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered
- System python3 (3.14) did not have pytest installed; switched to project venv (.venv/bin/python 3.13) which has the correct dependencies

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness
- StageComparator ready for use by ResolutionLoop (plan 01-04) and Orchestrator refactor (plan 01-03)
- TrackResult model from 01-01 integrates cleanly with compare_all_stages method
- No blockers for downstream plans

---
*Phase: 01-symmetric-double-programming*
*Completed: 2026-02-12*
