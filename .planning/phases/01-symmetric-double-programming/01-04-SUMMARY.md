---
phase: 01-symmetric-double-programming
plan: 04
subsystem: pipeline
tags: [resolution-loop, stage-comparator, adversarial-resolution, cascade-rerun, previous-error]

# Dependency graph
requires:
  - phase: 01-symmetric-double-programming (plan 02)
    provides: StageComparator for per-stage output comparison
  - phase: 01-symmetric-double-programming (plan 03)
    provides: Orchestrator with symmetric _run_track, TrackResult model
provides:
  - ResolutionLoop class with diagnosis, hint generation, and cascade re-runs
  - Orchestrator run() with post-hoc StageComparator + ResolutionLoop integration
  - Resolution metadata saved to consensus/resolution_log.json
  - Stage comparisons saved to consensus/stage_comparisons.json
  - Winning track selection for Medical Writer stats
affects: []

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Post-hoc stage comparison (Strategy C) -- both tracks run fully in parallel, then compare"
    - "Cascade downstream re-runs (sdtm->adam->stats, adam->stats) on resolution retry"
    - "Resolution hint injection via existing previous_error mechanism"
    - "Deterministic diagnosis heuristic (fewer rows = failing track, default track_b)"

key-files:
  created:
    - src/omni_agents/pipeline/resolution.py
    - tests/test_pipeline/test_resolution.py
  modified:
    - src/omni_agents/pipeline/orchestrator.py

key-decisions:
  - "Resolution hints injected via existing previous_error/make_retry_context mechanism (no new agent interface needed)"
  - "Cascade re-runs always include all downstream stages (sdtm retriggers adam+stats, adam retriggers stats)"
  - "_pick_best_track defaults to track_a (Gemini) in V1 when ambiguous"
  - "StageComparator.compare_all_stages called for re-comparison after cascade (not just single stage)"
  - "ConsensusJudge.compare_symmetric removed from run() flow, replaced by StageComparator + ResolutionLoop"

patterns-established:
  - "Strategy C post-hoc comparison: both tracks complete fully, then compare at every stage"
  - "Resolution loop bounded at max_iterations=2 by default (from ResolutionConfig)"
  - "Stage-appropriate suggested checks in STAGE_SUGGESTED_CHECKS dict"

# Metrics
duration: 5min
completed: 2026-02-12
---

# Phase 1 Plan 4: ResolutionLoop + Orchestrator Integration Summary

**Adversarial resolution loop with deterministic diagnosis, cascade re-runs, and hint injection via previous_error, integrated into orchestrator post-hoc stage comparison (Strategy C)**

## Performance

- **Duration:** 5 min
- **Started:** 2026-02-12T08:45:58Z
- **Completed:** 2026-02-12T08:51:08Z
- **Tasks:** 2
- **Files modified:** 3

## Accomplishments
- ResolutionLoop class with resolve, _diagnose, _generate_hint, _rerun_from_stage, _recompare_stage, _pick_best_track methods
- Orchestrator run() replaced ConsensusJudge.compare_symmetric with StageComparator.compare_all_stages + ResolutionLoop
- Resolution hints injected via existing previous_error mechanism (verified by agent contract tests for SDTMAgent, ADaMAgent, StatsAgent)
- Cascade downstream re-runs: SDTM triggers ADaM+Stats, ADaM triggers Stats
- Resolution metadata (resolution_log.json) and stage comparisons (stage_comparisons.json) saved to consensus directory
- 20 unit tests covering diagnosis, hint generation, cascade logic, pick_best_track, agent previous_error contract, and initialization

## Task Commits

Each task was committed atomically:

1. **Task 1: Create ResolutionLoop class** - `8b8d822` (feat)
2. **Task 2: Integrate stage comparison and resolution into orchestrator run()** - `4495a34` (feat)

## Files Created/Modified
- `src/omni_agents/pipeline/resolution.py` - ResolutionLoop class with adversarial resolution protocol
- `tests/test_pipeline/test_resolution.py` - 20 unit tests for resolution logic and agent contracts
- `src/omni_agents/pipeline/orchestrator.py` - run() updated with StageComparator + ResolutionLoop replacing ConsensusJudge

## Decisions Made
- Resolution hints use the existing `previous_error` context key, requiring no new agent interface
- Cascade re-runs always re-run ALL downstream stages (not just the disagreeing one) since upstream changes invalidate downstream outputs
- `_pick_best_track` returns "track_a" (Gemini) as default winner in V1 when ambiguous
- Full re-comparison via `compare_all_stages` after cascade (not just the single disagreeing stage)
- `ConsensusJudge.compare_symmetric` kept in consensus.py for backward compat but removed from orchestrator run() flow

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

None

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness
- Symmetric double programming architecture is complete (all 4 plans executed)
- Pipeline: Simulator -> parallel(Track A, Track B) -> StageComparator -> ResolutionLoop -> Medical Writer
- All stage-by-stage comparison and resolution metadata is persisted for auditability
- Resolution is opt-out via ResolutionConfig (enabled=True by default)

---
*Phase: 01-symmetric-double-programming*
*Completed: 2026-02-12*
