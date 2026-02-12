---
phase: 01-symmetric-double-programming
plan: 03
subsystem: pipeline
tags: [orchestrator, symmetric-tracks, track-isolation, cache-key, consensus, deprecation]

# Dependency graph
requires:
  - phase: 01-symmetric-double-programming/01-01
    provides: "TrackResult model, ScriptCache with track_id support"
provides:
  - "Symmetric _run_track method replacing asymmetric _run_track_a/_run_track_b"
  - "ConsensusJudge.compare_symmetric for same-format results.json"
  - "ProgressCallback.on_resolution_start and on_resolution_complete"
  - "Deprecated DoubleProgrammerAgent with DeprecationWarning"
affects: [01-symmetric-double-programming/01-04]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Generic _run_track parameterized by track_id and BaseLLM"
    - "Track-qualified step names (sdtm_track_a, adam_track_b)"
    - "Track-qualified cache keys via track_id in _run_agent"

key-files:
  created: []
  modified:
    - "src/omni_agents/pipeline/orchestrator.py"
    - "src/omni_agents/pipeline/consensus.py"
    - "src/omni_agents/agents/double_programmer.py"
    - "src/omni_agents/display/callbacks.py"

key-decisions:
  - "Used compare_symmetric bridge method on ConsensusJudge rather than modifying existing compare()"
  - "DoubleProgrammerAgent deprecated (DeprecationWarning) but not deleted for backward compat"
  - "Medical Writer uses track_a_result.stats_dir instead of hardcoded path"

patterns-established:
  - "Generic _run_track: single method parameterized by track_id/llm replaces per-track methods"
  - "Track-qualified naming: f'{stage}_{track_id}' for callbacks, state recording, and cache keys"

# Metrics
duration: 6min
completed: 2026-02-12
---

# Phase 01 Plan 03: Orchestrator Refactor Summary

**Symmetric _run_track method replacing asymmetric track runners, with track-qualified cache keys, callbacks, and ConsensusJudge.compare_symmetric bridge**

## Performance

- **Duration:** 6 min
- **Started:** 2026-02-12T08:38:30Z
- **Completed:** 2026-02-12T08:44:10Z
- **Tasks:** 2
- **Files modified:** 4

## Accomplishments
- Replaced _run_track_a and _run_track_b with a single generic _run_track method parameterized by track_id and BaseLLM
- Every _run_agent call passes track_id=track_id (3 occurrences) preventing cross-track cache collisions
- Every agent in _run_track followed by _record_step with track-qualified name f"{stage}_{track_id}"
- Added compare_symmetric to ConsensusJudge that reads same keys (table2/table3/metadata) from both results.json files
- Deprecated DoubleProgrammerAgent with DeprecationWarning on instantiation
- Added on_resolution_start and on_resolution_complete to ProgressCallback protocol

## Task Commits

Each task was committed atomically:

1. **Task 1: Refactor orchestrator to generic _run_track** - `b2106ac` (feat)
2. **Task 2: Deprecate DoubleProgrammerAgent and update callbacks** - `6d4b1b2` (feat)

## Files Created/Modified
- `src/omni_agents/pipeline/orchestrator.py` - Symmetric _run_track method, updated imports, updated run() fork section
- `src/omni_agents/pipeline/consensus.py` - Added compare_symmetric classmethod for same-format results.json comparison
- `src/omni_agents/agents/double_programmer.py` - DeprecationWarning on instantiation, updated docstrings
- `src/omni_agents/display/callbacks.py` - Track-qualified step name docs, on_resolution_start/complete callbacks

## Decisions Made
- Used compare_symmetric as a bridge method rather than modifying existing compare() -- preserves backward compatibility and makes it explicit this is temporary until Plan 04 replaces ConsensusJudge with StageComparator
- DoubleProgrammerAgent kept (not deleted) for backward compatibility -- only deprecated with warnings
- Medical Writer now uses track_a_result.stats_dir from TrackResult instead of hardcoded path construction

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered
None

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- Orchestrator now has symmetric tracks with generic _run_track
- Both tracks produce identical output structure (track_a/sdtm/, track_a/adam/, track_a/stats/ and track_b/sdtm/, track_b/adam/, track_b/stats/)
- ConsensusJudge.compare_symmetric is a temporary bridge -- Plan 04 will replace it with StageComparator + ResolutionLoop
- ProgressCallback already has on_resolution_start/complete for Plan 04's ResolutionLoop
- All 68 existing tests pass

---
*Phase: 01-symmetric-double-programming*
*Completed: 2026-02-12*
