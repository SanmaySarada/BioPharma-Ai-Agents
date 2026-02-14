# Research Summary: v1.2 Usability & Flexibility

**Researched:** 2026-02-14
**Files:** STACK.md, FEATURES.md, ARCHITECTURE.md, PITFALLS.md

---

## Executive Summary

All three v1.2 features are well-scoped and have no mutual dependencies. The existing stack covers most needs — **no new dependencies required**. `python-docx` is already installed for .docx parsing. The existing `BaseLLM` + Pydantic infrastructure handles structured extraction. Rich + asyncio already support interactive display with pause/resume.

**Highest risk:** Protocol parser — silent number misextraction in a regulated context (LLMs achieve only 49-66% exact-match on numeric extraction). Requires multi-layer validation: Pydantic bounds, source citations, mandatory human confirmation.

**Lowest risk:** CSR data dictionary removal — delete Section 8 from `medical_writer.j2`, write a deterministic CSV in Python. No LLM needed.

---

## Key Findings by Dimension

### Stack
- No new dependencies needed. `python-docx`, `pydantic`, `rich`, and `asyncio` cover all three features.
- Do NOT add Instructor or LangGraph — existing infrastructure is sufficient.
- Protocol parser reuses existing `BaseLLM` adapters. Add `extract_json()` to `response_parser.py`.
- Interactive mode uses `asyncio.get_event_loop().run_in_executor(None, input)` — standard pattern.

### Features
- **Protocol parser** is a differentiator (no competing tool does this), medium complexity.
- **CSR data dictionary** is a correctness fix — metadata belongs with data, not in narrative reports. Low complexity.
- **Interactive mode** is table stakes for any multi-stage pipeline. Medium complexity.
- Anti-features: Define-XML generation, step selection, protocol Q&A chatbot, dual-LLM parsing.

### Architecture
- Protocol parser: standalone class (NOT BaseAgent subclass), produces TrialConfig, runs before pipeline.
- Data dictionary: deterministic Python function (NOT LLM-generated), called after ADaM validation in `_run_track()`.
- Interactive mode: `InteractiveCallback` protocol extends `ProgressCallback`. Orchestrator calls `_checkpoint()` at phase boundaries. Display handles `input()` via `run_in_executor`.
- Pause points at 3 natural boundaries: after simulator, after parallel tracks, after comparison.

### Pitfalls
- **CRITICAL:** Protocol parser silent misextraction (PITFALL-01) — needs Pydantic bounds + human confirmation.
- **CRITICAL:** Don't use R officer `body_remove()` to strip data dictionary from CSR — modify the prompt template instead (PITFALL-02).
- **CRITICAL:** Don't add `input()` inside `asyncio.gather()` — pause between phases, not within parallel tracks (PITFALL-03).
- **MODERATE:** Rich Live display state lost after stop/start — refactor `start()` to preserve Progress instances (PITFALL-07).
- **MODERATE:** TrialConfig defaults silently fill gaps when LLM misses a field (PITFALL-04).

---

## Implications for Roadmap

Based on research, suggested phase structure:

### Phase 1: CSR Data Dictionary Extraction
- **Rationale:** Smallest scope, highest correctness impact, no LLM needed
- **Addresses:** Data dictionary as standalone file (FEATURES.md)
- **Avoids:** PITFALL-02 (orphaned cross-refs), PITFALL-06 (LLM still generates dict)
- **Files:** 2 new (data_dictionary.py, data_dictionary.csv template), 2 modified (medical_writer.j2, orchestrator.py)

### Phase 2: Interactive Execution Mode
- **Rationale:** Enables step-by-step review, prepares for protocol parser testing
- **Addresses:** Interactive mode with pause-between-stages (FEATURES.md)
- **Avoids:** PITFALL-03 (asyncio blocking), PITFALL-07 (Rich state loss), PITFALL-09 (CI breakage)
- **Files:** 2 new (interactive_display.py, InteractiveCallback), 3 modified (cli.py, orchestrator.py, callbacks.py)

### Phase 3: Protocol Parser Agent
- **Rationale:** Highest risk, benefits from interactive mode for human-in-the-loop verification
- **Addresses:** Natural-language .docx → structured config (FEATURES.md)
- **Avoids:** PITFALL-01 (silent misextraction), PITFALL-04 (silent defaults), PITFALL-05 (lost table text), PITFALL-08 (prompt engineering)
- **Files:** 2 new (protocol_parser.py, protocol_parser.j2), 2 modified (cli.py, response_parser.py)

**Phase ordering rationale:**
- Data dictionary first because it is the smallest and removes an anti-pattern from every pipeline run.
- Interactive mode second because it enables step-by-step inspection — useful for testing the protocol parser.
- Protocol parser last because it is the highest risk (silent misextraction in regulated context) and benefits from the interactive mode's human-in-the-loop review.

**Research flags for phases:**
- Phase 1: Standard patterns, no additional research needed.
- Phase 2: Rich Live stop/start interaction needs testing but pattern is proven in codebase.
- Phase 3: Likely needs deeper research on prompt engineering for number extraction. Budget 2-3x time for prompt iteration.

---

## Confidence Assessment

| Dimension | Confidence | Reason |
|-----------|------------|--------|
| Stack | HIGH | All libraries already installed, no new deps |
| Features | MEDIUM-HIGH | Feature patterns proven, implementation verified against codebase |
| Architecture | HIGH | Direct codebase analysis, component boundaries verified |
| Pitfalls | HIGH | Research papers confirm LLM extraction failure modes, asyncio patterns well-documented |

---

## Sources

See individual research files for full source lists. Key references:
- [LLM Numeric Extraction Accuracy](https://arxiv.org/html/2405.01686v2) — 49-66% exact match on clinical data
- [Pydantic for LLM Outputs](https://pydantic.dev/articles/llm-intro) — structured extraction patterns
- [CDISC Define-XML](https://www.cdisc.org/standards/data-exchange/define-xml) — metadata standards
- [Python asyncio Event Loop](https://docs.python.org/3/library/asyncio-dev.html) — blocking call patterns
