# Project State

## Current Position

Phase: 2 of 2 (Display Layer Update)
Plan: 1 of 1
Status: Phase complete
Last activity: 2026-02-12 - Completed 02-01-PLAN.md

Progress: [=100%] [##########] 5/5 plans

Plans:
- [x] 01-01-PLAN.md -- Foundation models + config + cache key fix
- [x] 01-02-PLAN.md -- StageComparator for per-stage output comparison
- [x] 01-03-PLAN.md -- Orchestrator refactor to symmetric _run_track
- [x] 01-04-PLAN.md -- ResolutionLoop + integrate into orchestrator
- [x] 02-01-PLAN.md -- Update PipelineDisplay steps + resolution callbacks + config.example.yaml documentation

## Decisions Made
- Pipeline architecture uses fork-join pattern with async tracks
- Track A = Gemini, Track B = GPT-4 (assigned LLMs)
- Docker isolation enforces track separation
- Deterministic consensus judge (no LLM) for comparison
- Error-feedback retry loop (max 3 attempts per agent)
- StageComparisonResult uses @property for has_disagreement/first_disagreement (not computed fields)
- track_id defaults to empty string for backward compat with non-track agents
- ResolutionConfig defaults to enabled=True, max_iterations=2 (opt-out)
- STATS_TOLERANCES defined locally in stage_comparator.py to avoid coupling with ConsensusJudge
- All StageComparator methods are classmethods (no instance state) following SchemaValidator pattern
- compare_symmetric bridge method on ConsensusJudge rather than modifying existing compare()
- DoubleProgrammerAgent deprecated (DeprecationWarning) but not deleted for backward compat
- Medical Writer uses track_a_result.stats_dir from TrackResult instead of hardcoded path
- Resolution hints injected via existing previous_error/make_retry_context mechanism (no new agent interface)
- Cascade re-runs always include all downstream stages (sdtm retriggers adam+stats, adam retriggers stats)
- _pick_best_track defaults to track_a (Gemini) in V1 when ambiguous
- Full re-comparison via compare_all_stages after cascade (not just single stage)
- ConsensusJudge.compare_symmetric removed from run() flow, replaced by StageComparator + ResolutionLoop
- Resolution is a meta-activity, not a pipeline step -- no row in _STEPS table
- Non-interactive mode gets explicit resolution log lines; interactive mode relies on step retry callbacks

## Known Constraints
- R code must execute in Docker containers
- Track isolation must be maintained (no cross-reading)
- All R packages must be pre-installed in Docker image
- API keys via environment variables only

## Session Continuity

Last session: 2026-02-12T22:06:26Z
Stopped at: Completed 02-01-PLAN.md (phase complete)
Resume file: None
