# Roadmap

## Milestone 1: Symmetric Double Programming with Adversarial Resolution

### Phase 1: Symmetric Double Programming Architecture
Redesign Track B to perform the full SDTM -> ADaM -> Stats pipeline independently (mirroring Track A), run both tracks in parallel, implement stage-by-stage comparison, and build an adversarial resolution loop where disagreeing LLMs diagnose failures and retry with targeted hints.

**Goal:** Both tracks produce full regulatory-grade outputs that are compared at every stage, with automated resolution when they diverge.

**Plans:** 4 plans

Plans:
- [ ] 01-01-PLAN.md -- Foundation models (TrackResult, StageComparison, ResolutionHint, ResolutionResult) + config + cache key fix
- [ ] 01-02-PLAN.md -- StageComparator for per-stage output comparison (SDTM, ADaM, Stats)
- [ ] 01-03-PLAN.md -- Orchestrator refactor to symmetric _run_track + deprecate DoubleProgrammerAgent
- [ ] 01-04-PLAN.md -- ResolutionLoop + integrate stage comparison and resolution into orchestrator
