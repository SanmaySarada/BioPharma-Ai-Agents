---
phase: 03-stderr-filtering-error-classification
verified: 2026-02-12T23:41:03Z
status: passed
score: 3/3 must-haves verified
---

# Phase 3: Stderr Filtering & Error Classification Verification Report

**Phase Goal:** Real R errors are visible, correctly classified, and fed back to the LLM for effective retries
**Verified:** 2026-02-12T23:41:03Z
**Status:** passed
**Re-verification:** No -- initial verification

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | When an R script fails, the actual R error is visible in the terminal error panel (not package loading noise) | VERIFIED | `filter_r_stderr()` is called at line 274 of `retry.py` immediately after Docker execution, before all 7+ stderr consumption points including `NonRetriableError(docker_result.stderr[:500])` and `MaxRetriesExceededError(last_stderr)`. Test `test_filtered_stderr_fits_truncation_window` proves the full survminer+tidyverse stderr reduces to under 500 chars after filtering, so the truncation window contains the real error. |
| 2 | `classify_error` correctly classifies errors from scripts that load survminer/tidyverse (no false positives on "object is masked") | VERIFIED | Old `code_patterns = ["object", ...]` bare substring list fully removed (confirmed via git diff). Replaced with `_CODE_BUG_REGEX` using `r"object\s+'[^']+'\s+not found"` which matches "object 'x' not found" but NOT "The following object is masked". Test `test_classify_object_masked_not_code_bug` directly verifies no false positive. Test `test_classify_object_not_found_is_code_bug` verifies real errors still detected. Test `test_filtered_survminer_tidyverse_classified_correctly` proves end-to-end: filtered survminer+tidyverse stderr with error is classified as CODE_BUG from "Error in readRDS", not from "object is masked". |
| 3 | LLM retry attempts receive filtered stderr with the actual error, enabling effective code fixes | VERIFIED | At line 320 of `retry.py`: `last_error = docker_result.stderr` -- this `docker_result` has already been replaced with a filtered copy at line 271-277. `last_error` is then passed to `generate_code_fn(last_error, attempt_num)` at line 262 on the next iteration, which is the LLM code generation callback. The LLM receives only the real error, not package loading noise. |

**Score:** 3/3 truths verified

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `src/omni_agents/pipeline/stderr_filter.py` | `filter_r_stderr()` function and `_NOISE_PATTERNS` constant | VERIFIED (79 lines, 13 noise patterns, 1 exported function, no stubs) | Substantive implementation with safety-net for Error lines, strip of leading/trailing blanks. Imported by retry.py and pipeline __init__.py. |
| `tests/test_pipeline/test_stderr_filter.py` | Comprehensive tests for filter_r_stderr | VERIFIED (168 lines, 13 test cases, all passing) | Uses real R stderr samples (tidyverse Unicode banner, survminer loading, dplyr masking). Covers edge cases: empty input, error preservation, legitimate warnings, mixed noise+errors. |
| `src/omni_agents/pipeline/retry.py` | Fixed classify_error + filter wiring | VERIFIED (333 lines, filter_r_stderr imported and called at chokepoint, old "object" pattern removed) | `_CODE_BUG_REGEX` (4 compiled regex) and `_CODE_BUG_SUBSTRINGS` (8 safe patterns) replace old dangerous `code_patterns` list. Filter applied at line 271-277 before all downstream consumers. |
| `tests/test_pipeline/test_retry.py` | Tests for classify_error fixes and integration | VERIFIED (197 lines, 13 test cases, all passing) | 10 classify_error unit tests covering all ErrorClassification values + 3 end-to-end integration tests (filter+classify, truncation window, noise-only). |
| `src/omni_agents/pipeline/__init__.py` | Re-export filter_r_stderr | VERIFIED | `filter_r_stderr` imported from `stderr_filter` and listed in `__all__`. |

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| `retry.py` | `stderr_filter.py` | `from omni_agents.pipeline.stderr_filter import filter_r_stderr` | WIRED | Import at line 30, called at line 274 |
| `retry.py` | `DockerResult` | `DockerResult(...)` constructor | WIRED | New DockerResult created at lines 271-277 with filtered stderr |
| `pipeline/__init__.py` | `stderr_filter.py` | `from omni_agents.pipeline.stderr_filter import filter_r_stderr` | WIRED | Import at line 22, in `__all__` at line 38 |
| `test_stderr_filter.py` | `stderr_filter.py` | `from omni_agents.pipeline.stderr_filter import filter_r_stderr` | WIRED | Import at line 3, used in all 13 tests |
| `test_retry.py` | `retry.py` | `from omni_agents.pipeline.retry import classify_error` | WIRED | Import at line 12, used in 13 tests |
| `test_retry.py` | `stderr_filter.py` | `from omni_agents.pipeline.stderr_filter import filter_r_stderr` | WIRED | Import at line 13, used in 3 integration tests |
| `execute_with_retry` filter | all downstream consumers | DockerResult replacement at line 271-277 | WIRED | `_is_real_error` (L283), `classify_error` (L297), `NonRetriableError` stderr[:500] (L314), `last_error` LLM feedback (L320), `MaxRetriesExceeded` stderr[:500] (L324) -- all consume the already-filtered `docker_result.stderr` |

### Requirements Coverage

| Requirement | Status | Evidence |
|-------------|--------|----------|
| STDERR-01: Strip R package loading messages from stderr | SATISFIED | `_NOISE_PATTERNS` tuple with 13 compiled regex patterns covers tidyverse banner, conflict lines, checkmark lines, package loading, object masking, Registered S3, indented continuations, box-drawing decoration, and more |
| STDERR-02: Preserve actual R errors and warnings in filtered stderr | SATISFIED | Safety-net: lines starting with Error/error are NEVER filtered (tested by `test_error_lines_never_filtered`). Legitimate warnings preserved (tested by `test_legitimate_warning_preserved`, `test_legitimate_warning_in_sqrt_preserved`) |
| STDERR-03: Apply stderr filtering before error classification, LLM retry feedback, and error display | SATISFIED | Single chokepoint at line 271-277 of `retry.py` replaces DockerResult before all 7+ consumption points |
| ERRCLASS-01: Fix "object" pattern to not false-match on "The following object is masked" | SATISFIED | Old `"object"` bare substring removed. Replaced with `r"object\s+'[^']+'\s+not found"` regex. Test `test_classify_object_masked_not_code_bug` directly verifies |
| ERRCLASS-02: Audit all code_patterns for similar false-positive risks | SATISFIED | Old dangerous patterns `"unexpected"`, `"error in"`, `"could not find"` all replaced. `"unexpected"` split to `"unexpected symbol"`, `"unexpected string"`, `"unexpected '"`. `"error in"` replaced with anchored `^Error in ` regex. `"could not find"` replaced with `"could not find function"` regex |
| ERRCLASS-03: Make error patterns match in error-context only | SATISFIED | `_CODE_BUG_REGEX` uses `re.MULTILINE` anchored `^Error in ` and specific phrases like `object\s+'[^']+'\s+not found` that only appear in error context, not package loading noise |
| ERRDSP-01: Show actual R error in terminal error panel and pipeline logs | SATISFIED | `NonRetriableError` and `MaxRetriesExceededError` both use `docker_result.stderr[:500]` which is already filtered. `AgentAttempt.docker_result` stored with filtered stderr, so logging and display callbacks get clean output |
| ERRDSP-02: Ensure 500-char truncation window contains real error | SATISFIED | Test `test_filtered_stderr_fits_truncation_window` proves: full survminer+tidyverse stderr (800+ chars) reduces to under 500 chars after filtering, ensuring truncation window contains the actual error |

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| (none) | - | - | - | No anti-patterns found in any modified files |

Scanned all 4 artifacts for TODO/FIXME/placeholder/stub patterns, empty returns, and console.log. Zero findings.

### Human Verification Required

### 1. End-to-end pipeline run with survminer/tidyverse R script

**Test:** Run the full pipeline with an R script that loads survminer and tidyverse and contains a deliberate error (e.g., referencing undefined variable). Observe the terminal error panel.
**Expected:** The error panel shows only the actual R error (e.g., "Error in eval(expr) : object 'x' not found"), not pages of package loading messages. The LLM retry should receive the clean error and attempt a meaningful fix.
**Why human:** Requires Docker, a real LLM call, and visual inspection of the terminal display. Cannot verify programmatically without running the full pipeline stack.

### 2. Visual confirmation of error panel display

**Test:** During a pipeline failure, check that the Rich terminal display shows the filtered error, not truncated package noise.
**Expected:** Error message in the terminal panel is concise and actionable.
**Why human:** Display rendering depends on Rich library layout and terminal width. Structural verification confirms the data is clean, but visual confirmation needs a human.

### Gaps Summary

No gaps found. All 3 observable truths are verified. All 8 requirements mapped to this phase are satisfied. All 5 artifacts exist, are substantive (79-333 lines), contain no stubs, and are properly wired. All 26 phase-specific tests pass. Full test suite of 114 tests passes with zero regressions.

The phase goal -- "Real R errors are visible, correctly classified, and fed back to the LLM for effective retries" -- is achieved through:

1. **filter_r_stderr()**: A 13-pattern regex filter that strips all R package loading noise (tidyverse banners, survminer loading, dplyr masking, Registered S3 methods, etc.) while preserving real Error lines and legitimate warnings.

2. **Single chokepoint wiring**: filter_r_stderr is called exactly once in execute_with_retry immediately after Docker execution (line 271-277), replacing the DockerResult with filtered stderr before ALL 7+ downstream consumers (error detection, classification, error messages, LLM feedback, logging, display).

3. **Context-aware classify_error**: The old dangerous `code_patterns = ["object", "unexpected", "error in", ...]` bare substring list is fully replaced with `_CODE_BUG_REGEX` (4 compiled regex with word boundaries and line anchors) and `_CODE_BUG_SUBSTRINGS` (8 unambiguous patterns). "object 'x' not found" is correctly classified as CODE_BUG; "The following object is masked" is not.

---

_Verified: 2026-02-12T23:41:03Z_
_Verifier: Claude (gsd-verifier)_
