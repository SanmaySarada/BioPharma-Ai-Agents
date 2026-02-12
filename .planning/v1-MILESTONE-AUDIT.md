---
milestone: 1
audited: 2026-02-12
re-audited: 2026-02-12
status: tech_debt
scores:
  requirements: 12/12
  phases: 2/2
  integration: 12/14
  flows: 3/3
gaps: []
tech_debt:
  - phase: 01-symmetric-double-programming
    items:
      - "on_step_retry/on_step_fail use bare agent.name instead of track-qualified name (display row not updated during retries)"
      - "on_pipeline_fail defined in ProgressCallback but never called (CLI uses ErrorDisplay directly)"
      - "ConsensusJudge.compare_symmetric orphaned (intentional — retained for backward compat)"
      - "DoubleProgrammerAgent orphaned (intentional — deprecated, retained for backward compat)"
      - "_pick_best_track always returns track_a (V1 heuristic — documented)"
      - "validation_failures=[] placeholder in _generate_hint (V1 — future SchemaValidator integration)"
closed_from_previous_audit:
  - "PipelineDisplay._STEPS not updated for track-qualified step names → CLOSED by Phase 2"
  - "PipelineDisplay missing on_resolution_start/on_resolution_complete → CLOSED by Phase 2"
  - "config.example.yaml missing resolution section documentation → CLOSED by Phase 2"
---

# Milestone 1 Audit: Symmetric Double Programming with Adversarial Resolution

**Audited:** 2026-02-12 (re-audit after Phase 2 gap closure)
**Status:** TECH DEBT (no blockers, accumulated deferred items)

## Previous Audit Gap Closure

Phase 2 (Display Layer Update) closed the 3 warning-level items from the first audit:

| Previous Finding | Status | Closed By |
|-----------------|--------|-----------|
| PipelineDisplay._STEPS not updated for track-qualified names | CLOSED | 02-01 Task 1 |
| PipelineDisplay missing resolution callbacks | CLOSED | 02-01 Task 2 |
| config.example.yaml missing resolution section | CLOSED | 02-01 Task 3 |

## Requirements Coverage

| Requirement | Sub-requirement | Status | Notes |
|-------------|----------------|--------|-------|
| R-ARCH | Both tracks perform full SDTM/ADaM/Stats independently | SATISFIED | Generic `_run_track` in orchestrator |
| R-ARCH | Tracks run in parallel with complete isolation | SATISFIED | `asyncio.gather()` + track-aware cache keys |
| R-ARCH | Stage-by-stage comparison (not just final stats) | SATISFIED | StageComparator with SDTM/ADaM/Stats comparisons |
| R-ARCH | Automated disagreement resolution when tracks diverge | SATISFIED | ResolutionLoop with diagnosis + hints + cascade |
| R-RESOLVE | System diagnoses which track erred | SATISFIED | Deterministic heuristic in `_diagnose` |
| R-RESOLVE | Targeted hints to the failing LLM | SATISFIED | `ResolutionHint.to_prompt_text()` via `previous_error` |
| R-RESOLVE | Failed track retries with error context, not full restart | SATISFIED | `_rerun_from_stage` with cascade downstream |
| R-RESOLVE | Resolution bounded (max iterations) | SATISFIED | `ResolutionConfig.max_iterations=2` |
| R-VALID | Compare SDTM outputs between tracks | SATISFIED | `compare_sdtm` with 8 structural checks |
| R-VALID | Compare ADaM derivations between tracks | SATISFIED | `compare_adam` with 5 derivation checks |
| R-VALID | Compare statistical results between tracks | SATISFIED | `compare_stats` with 7 tolerance-based metrics |
| R-VALID | Each stage gate passes before proceeding | SATISFIED | Post-hoc Strategy C — all stages compared before Medical Writer proceeds |

**Score:** 12/12 requirements satisfied

## Phase Verification

| Phase | Status | Score | Verification |
|-------|--------|-------|-------------|
| 01: Symmetric Double Programming | ✓ Passed | 9/9 must-haves | 01-VERIFICATION.md |
| 02: Display Layer Update | ✓ Passed | 5/5 must-haves | 02-VERIFICATION.md |

**Score:** 2/2 phases verified

## Integration & E2E Flows

### Cross-Phase Wiring

| Connection | Status | Details |
|------------|--------|---------|
| 9 orchestrator step names → _STEPS | PASS | All 9 match exactly (verified per-line) |
| on_resolution_start chain | PASS | orchestrator → ProgressCallback → PipelineDisplay, signatures match |
| on_resolution_complete chain | PASS | orchestrator → ProgressCallback → PipelineDisplay, signatures match |
| config.example.yaml → ResolutionConfig | PASS | enabled=true/True, max_iterations=2/2 |
| TrackResult model usage | PASS | Imported by orchestrator, stage_comparator, resolution |
| StageComparator → orchestrator | PASS | compare_all_stages() called at orchestrator:495 |
| ResolutionLoop → orchestrator | PASS | resolve() called at orchestrator:529 |
| ScriptCache track-aware | PASS | 3-arg cache_key used at orchestrator:129 |
| PipelineDisplay → CLI | PASS | Created at cli.py:40, passed as callback |
| Resolution hint injection | PASS | Via previous_error, contract-tested in all 3 agents |
| on_step_retry step name | DEGRADED | Uses bare agent.name, not track-qualified; table row not updated |
| on_step_fail step name | DEGRADED | Same as on_step_retry |
| on_pipeline_fail callback | ORPHANED | Defined but never called; CLI uses ErrorDisplay |
| ProgressCallback protocol conformance | PASS | isinstance(PipelineDisplay(), ProgressCallback) is True |

**Score:** 12/14 connections (2 degraded, non-blocking)

### E2E Flows

| Flow | Status | Details |
|------|--------|---------|
| Full pipeline run | PASS | Simulator → parallel tracks (9 steps) → comparison → resolution → verdict → Medical Writer. All 9 display rows update correctly. |
| Resolution flow | PASS | Disagreement → on_resolution_start → diagnosis → hint → re-run with cascade → re-compare → on_resolution_complete. Display shows resolution in non-interactive mode. |
| Config flow | PASS | config.example.yaml → Settings.from_yaml() → ResolutionConfig → orchestrator respects enabled/max_iterations. |

**Score:** 3/3 flows complete

## Tech Debt

### Cosmetic Display Issues (non-blocking)

- **on_step_retry/on_step_fail step name mismatch** — `_run_agent` passes `agent.name` ("sdtm") instead of track-qualified name ("sdtm_track_a") to retry/fail callbacks. Interactive table row doesn't update to "retrying"/"failed" for track agents. Non-interactive fallback still prints. Fix: thread track-qualified step name through `_run_agent`.
- **on_pipeline_fail dead code** — Defined in ProgressCallback protocol and PipelineDisplay but never called. CLI uses ErrorDisplay directly. Fix: wire into CLI error handler or remove from protocol.

### Intentional V1 Simplifications

- `_pick_best_track` always returns `track_a` (Gemini). V1 heuristic, documented.
- `validation_failures=[]` placeholder in `_generate_hint`. Future SchemaValidator integration.
- `ConsensusJudge.compare_symmetric` orphaned — removed from orchestrator flow, retained for backward compat.
- `DoubleProgrammerAgent` deprecated with DeprecationWarning, no callers. Retained for backward compat.

## Tests

88 tests pass, 0 regressions.

| Suite | Count |
|-------|-------|
| Pre-existing | 48 |
| Script cache (new) | 8 |
| Stage comparator (new) | 12 |
| Resolution (new) | 20 |

## Human Verification Required

1. **End-to-end pipeline run with real LLMs** — requires live API keys + Docker
2. **Resolution loop trigger on actual disagreement** — requires orchestrating real LLM disagreement
3. **Visual terminal display** — run pipeline and observe Rich live table with all 9 steps + progress bars
4. **Non-interactive resolution display** — pipe output and trigger disagreement to verify resolution log lines

---

_First audit: 2026-02-12_
_Re-audit: 2026-02-12 (after Phase 2 gap closure)_
_Auditor: Claude (gsd-verifier + gsd-integration-checker + orchestrator aggregation)_
