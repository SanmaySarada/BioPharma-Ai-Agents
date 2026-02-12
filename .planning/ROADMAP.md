# Roadmap

## Milestone 1: Symmetric Double Programming with Adversarial Resolution

### Phase 1: Symmetric Double Programming Architecture
Redesign Track B to perform the full SDTM -> ADaM -> Stats pipeline independently (mirroring Track A), run both tracks in parallel, implement stage-by-stage comparison, and build an adversarial resolution loop where disagreeing LLMs diagnose failures and retry with targeted hints.

**Goal:** Both tracks produce full regulatory-grade outputs that are compared at every stage, with automated resolution when they diverge.

**Status:** ✓ Complete (2026-02-12)
**Plans:** 4 plans

Plans:
- [x] 01-01-PLAN.md -- Foundation models (TrackResult, StageComparison, ResolutionHint, ResolutionResult) + config + cache key fix
- [x] 01-02-PLAN.md -- StageComparator for per-stage output comparison (SDTM, ADaM, Stats)
- [x] 01-03-PLAN.md -- Orchestrator refactor to symmetric _run_track + deprecate DoubleProgrammerAgent
- [x] 01-04-PLAN.md -- ResolutionLoop + integrate stage comparison and resolution into orchestrator

### Phase 2: Display Layer Update
Update PipelineDisplay for the symmetric architecture — track-qualified step names, resolution callbacks, and config documentation. Closes tech debt from milestone audit.

**Goal:** CLI terminal display accurately reflects all pipeline steps (both tracks, stage comparison, resolution) and config.example.yaml documents resolution settings.

**Gap Closure:** Closes display/UX warning and config documentation gap from v1-MILESTONE-AUDIT.md
**Plans:** TBD
