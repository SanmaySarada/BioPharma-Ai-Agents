# omni-ai-agents

Multi-LLM clinical trial simulation and analysis pipeline. Two LLMs (Gemini + GPT-4) independently analyze synthetic clinical trial data through separate code paths; a deterministic Consensus Judge compares results to catch errors -- computational double programming for regulated biostatistics.

## Tech Stack
- Python 3.13+, R 4.5.2
- Docker (isolated R execution)
- Gemini 2.5-pro (Track A), GPT-4o (Track B)
- asyncio, Typer CLI, Rich display, Pydantic config

## Current State
Pipeline is functional end-to-end with symmetric double programming. Both Track A (Gemini) and Track B (GPT-4) independently run the full SDTM->ADaM->Stats pipeline. StageComparator performs per-stage comparison. ResolutionLoop handles disagreements with diagnosis, targeted hints, and cascading re-runs. PipelineDisplay shows all 9 pipeline steps with resolution callbacks. 88 tests passing.

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
*Last updated: 2026-02-12 after v1.0 milestone*
