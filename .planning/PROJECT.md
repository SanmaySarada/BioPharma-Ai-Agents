# omni-ai-agents

Multi-LLM clinical trial simulation and analysis pipeline. Two LLMs (Gemini + GPT-4) independently analyze synthetic clinical trial data through separate code paths; a deterministic Consensus Judge compares results to catch errors -- computational double programming for regulated biostatistics.

## Tech Stack
- Python 3.13+, R 4.5.2
- Docker (isolated R execution)
- Gemini 2.5-pro (Track A), GPT-4o (Track B)
- asyncio, Typer CLI, Rich display, Pydantic config

## Current Milestone: v1.1 Pipeline Reliability

**Goal:** Fix error handling so the pipeline reliably completes even when one track's LLM-generated R code fails, and make R errors visible for effective debugging and retry.

**Target features:**
- Filter R package loading noise from stderr before error classification, display, and LLM retry feedback
- Fix overly broad `classify_error` patterns that false-positive on benign R output (e.g., "object" matching "The following object is masked")
- Show the actual R error in logs and terminal display, not truncated package loading messages
- Per-track error isolation: one track failure should not crash the pipeline — continue with the surviving track

## Current State
Pipeline is functional end-to-end with symmetric double programming. Both Track A (Gemini) and Track B (GPT-4) independently run the full SDTM->ADaM->Stats pipeline. StageComparator performs per-stage comparison. ResolutionLoop handles disagreements with diagnosis, targeted hints, and cascading re-runs. PipelineDisplay shows all 9 pipeline steps with resolution callbacks. 88 tests passing.

**Known issue (triggering v1.1):** Track B stats agent fails all 3 retries because R package loading stderr noise (ggplot2, survminer, tidyverse) hides the actual error. Error display truncates at 500 chars, all consumed by noise. The `classify_error` "object" pattern false-matches on "The following object is masked". The pipeline then crashes both tracks via `asyncio.gather()` exception propagation.

## Requirements

### Validated

- [x] Symmetric double programming with Track A (Gemini) and Track B (GPT-4) — v1.0
- [x] Per-stage comparison with tolerance-based statistical matching — v1.0
- [x] Resolution loop with diagnosis, hints, and cascading re-runs — v1.0
- [x] Track-aware script caching — v1.0
- [x] Pipeline display with 9 steps and resolution callbacks — v1.0

### Active

- [ ] Strip R package loading noise from stderr before classification, display, and retry feedback
- [ ] Fix `classify_error` patterns to avoid false positives on benign R output
- [ ] Show actual R error (not truncated noise) in error display and logs
- [ ] Per-track error isolation in `asyncio.gather()` — surviving track continues

### Out of Scope

- Smarter `_pick_best_track` heuristic — deferred to v2.0
- Schema validator integration in resolution hints — deferred to v2.0

## Key Decisions
- Fork-join parallel tracks with asyncio.gather() -- ✓ Good
- Deterministic consensus judge (no LLM for comparison) -- ✓ Good
- Strategy C post-hoc comparison (both tracks complete, then compare all stages) -- ✓ Good
- Resolution hints via existing previous_error mechanism -- ✓ Good
- _pick_best_track defaults to track_a in V1 -- Pending (needs smarter heuristic in V2)

## Constraints
- R code must execute in Docker containers
- Track isolation must be maintained (no cross-reading)
- All R packages must be pre-installed in Docker image
- API keys via environment variables only

---
*Last updated: 2026-02-12 after v1.1 milestone start*
