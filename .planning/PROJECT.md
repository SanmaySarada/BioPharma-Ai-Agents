# omni-ai-agents

Multi-LLM clinical trial simulation and analysis pipeline. Two LLMs (Gemini + GPT-4) independently analyze synthetic clinical trial data through separate code paths; a deterministic Consensus Judge compares results to catch errors -- computational double programming for regulated biostatistics.

## Tech Stack
- Python 3.13+, R 4.5.2
- Docker (isolated R execution)
- Gemini 2.5-pro (Track A), GPT-4o (Track B)
- asyncio, Typer CLI, Rich display, Pydantic config

## Current Milestone: v1.2 Usability & Flexibility

**Goal:** Make the pipeline configurable from a natural-language protocol document, clean up the CSR output, and add an interactive execution mode for step-by-step review.

**Target features:**
- Protocol parser agent: reads a Word/text protocol document (natural-language trial description) and extracts structured trial parameters into the config format, so users edit a plain-English doc instead of YAML
- CSR cleanup: remove data dictionary from the final Word report; data dictionary should be written as a standalone file in the relevant output folder (sdtm/adam) instead
- Interactive execution mode: add a phase-by-phase mode where the pipeline pauses after each step and waits for the user to press Enter before continuing (alongside existing autonomous mode)

## Current State
Pipeline completes end-to-end reliably. Inf trap and survfit column-name bugs fixed via prompt guardrails and validation. 117 tests passing. Both tracks produce full SDTM->ADaM->Stats independently. Medical writer generates CSR as Word document.

## Requirements

### Validated

- [x] Symmetric double programming with Track A (Gemini) and Track B (GPT-4) — v1.0
- [x] Per-stage comparison with tolerance-based statistical matching — v1.0
- [x] Resolution loop with diagnosis, hints, and cascading re-runs — v1.0
- [x] Track-aware script caching — v1.0
- [x] Pipeline display with 9 steps and resolution callbacks — v1.0
- [x] Strip R package loading noise from stderr before classification, display, and retry feedback — v1.1
- [x] Fix `classify_error` patterns to avoid false positives on benign R output — v1.1
- [x] ADaM validation catches Inf trap (n_censored==0, event_rate>95%) — v1.1
- [x] Stats prompt specifies exact survfit summary column names — v1.1

### Active

- [ ] Protocol parser agent: natural-language .docx → structured trial config
- [ ] Data dictionary as standalone file in sdtm/adam folder, not in CSR
- [ ] Interactive execution mode (pause between steps, Enter to continue)

### Out of Scope

- Smarter `_pick_best_track` heuristic — deferred to v2.0
- Schema validator integration in resolution hints — deferred to v2.0
- Per-track error isolation in `asyncio.gather()` — deferred (pipeline now reliable enough)

## Key Decisions
- Fork-join parallel tracks with asyncio.gather() -- ✓ Good
- Deterministic consensus judge (no LLM for comparison) -- ✓ Good
- Strategy C post-hoc comparison (both tracks complete, then compare all stages) -- ✓ Good
- Resolution hints via existing previous_error mechanism -- ✓ Good
- _pick_best_track defaults to track_a in V1 -- Pending (needs smarter heuristic in V2)
- Prompt guardrails for R edge cases (Inf, survfit columns) -- ✓ Good
- ADaM validation sanity checks (n_censored, event_rate) -- ✓ Good (note: thresholds assume dropout_rate > 0)

## Constraints
- R code must execute in Docker containers
- Track isolation must be maintained (no cross-reading)
- All R packages must be pre-installed in Docker image
- API keys via environment variables only
- Protocol document changes should not require code changes — only numbers/parameters vary

---
*Last updated: 2026-02-12 after v1.2 milestone start*
