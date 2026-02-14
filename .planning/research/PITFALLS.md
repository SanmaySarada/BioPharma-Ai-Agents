# Domain Pitfalls: v1.2 Usability & Flexibility

**Domain:** Multi-LLM clinical trial pipeline -- protocol parsing, CSR document modification, interactive execution
**Researched:** 2026-02-14
**Confidence:** HIGH (verified against codebase architecture; research papers confirm LLM number extraction failure modes)

---

## Critical Pitfalls

Mistakes that cause wrong results (regulated context: wrong but plausible output is worse than a crash).

---

### PITFALL-01: Silent Number Misextraction by Protocol Parser

**What goes wrong:** The LLM extracts a number from the protocol document that is wrong but structurally valid. Examples from published clinical trial extraction research (arxiv 2405.01686):

- `n_subjects=30` instead of `300` (dropped trailing zero -- order of magnitude error)
- `treatment_sbp_mean=12.0` instead of `120.0` (decimal point shifted)
- `dropout_rate=10` instead of `0.10` (missing decimal, treated as percentage vs fraction)
- `randomization_ratio="1:2"` instead of `"2:1"` (inverted ratio)
- `placebo_sbp_sd=10.0` hallucinated when document says `20.0` (LLM interpolated from context)
- `baseline_sbp_mean=140.0` extracted from the wrong paragraph (picked placebo value instead of baseline)

**Why it happens:** LLMs achieve only ~49-66% exact-match accuracy on continuous numeric extraction from clinical documents (GPT-4 best case). Common failure modes:
1. **Context confusion** -- extracting a value from the wrong section when similar numbers appear in multiple places
2. **Unit/scale confusion** -- confusing percentage (10%) with decimal fraction (0.10), or SD with SE
3. **Hallucination** -- fabricating a plausible value when the document is ambiguous or the parameter is not explicitly stated
4. **Format confusion** -- confusing means with medians, or baseline with post-treatment values

**Consequences:** The pipeline produces a complete, professional-looking CSR with wrong statistical results. Because `TrialConfig` has defaults for every field (`n_subjects=300`, `treatment_sbp_mean=120.0`, etc.), a partially-extracted config that misses a field silently uses the default -- which may or may not match the protocol document. The user sees no error. The double-programming architecture catches *inter-track* disagreement but cannot catch a systematically wrong input parameter that both tracks use identically.

**Prevention (multi-layer):**

1. **Pydantic validation with domain constraints on `TrialConfig`:**
   ```python
   class TrialConfig(BaseModel):
       n_subjects: int = Field(ge=10, le=10000)  # no trial has 3 subjects
       dropout_rate: float = Field(ge=0.0, le=1.0)  # must be fraction, not percentage
       missing_rate: float = Field(ge=0.0, le=1.0)
       treatment_sbp_mean: float = Field(ge=50, le=250)  # physiological range
       placebo_sbp_mean: float = Field(ge=50, le=250)
       baseline_sbp_mean: float = Field(ge=50, le=250)
       age_mean: float = Field(ge=18, le=100)
   ```

2. **Mandatory human confirmation before pipeline execution:**
   Display every extracted parameter alongside the source text snippet where the LLM claims it found the value. Require explicit user confirmation. This is non-negotiable for regulated biostatistics.

3. **Source citation requirement in LLM prompt:**
   Require the LLM to return each extracted value with the exact quote from the document where it found it. If the LLM cannot cite a source line, flag the value as potentially hallucinated.

4. **Completeness check:**
   Compare extracted fields against `TrialConfig` field list. Any field not explicitly extracted from the document (falling back to default) must be flagged and confirmed by user.

5. **Round-trip validation:**
   After extraction, generate a natural-language summary of the extracted parameters and ask the user: "Does this match your protocol?" This catches errors that individual field validation misses (e.g., "300 subjects randomized 2:1 Treatment:Placebo" is a coherent cross-field check).

**Detection (warning signs):**
- LLM returns a value that equals a `TrialConfig` default exactly -- possibly failed to extract and used the default
- LLM cannot provide a source citation for a value
- Extracted value is at a physiological boundary (e.g., `age_mean=18` -- suspicious, probably wrong)
- Multiple parameters share suspiciously round values

**Phase mapping:** Protocol Parser Agent phase. Build validation layer BEFORE building the extraction prompt. Test with intentionally adversarial protocol documents (ambiguous phrasing, values that look like other fields).

---

### PITFALL-02: Orphaned Cross-References After Data Dictionary Removal

**What goes wrong:** The medical writer's R code uses `run_reference("bkm_table1")`, `run_reference("bkm_table2")`, `run_reference("bkm_table3")`, and `run_reference("bkm_figure1")` to create Word cross-references. The data dictionary is currently Section 8 in the CSR. If the removal approach modifies document structure (re-ordering sections, removing paragraphs with `body_remove()`), Word cross-references can break, producing "Error! Reference source not found" in the final document.

**Why it happens:** Word cross-references are internally stored as field codes pointing to named bookmarks. The `officer` R package's `body_remove()` function removes one paragraph at a time and requires cursor positioning via `cursor_reach()`. If the removal loop accidentally removes a bookmarked paragraph (e.g., the heading above a table that contains the bookmark), the cross-reference in the narrative section becomes orphaned. The officer package does NOT warn you when this happens -- the document generates without error, but shows broken references when opened in Word.

**Consequences:** The CSR opens with "Error! Reference source not found" where table/figure numbers should appear. In a regulated document, this is immediately disqualifying.

**Prevention:**

1. **Do not use `body_remove()` to strip the data dictionary post-hoc.** Instead, modify the medical writer prompt template to NOT generate the data dictionary section in the first place. The data dictionary should be generated as a separate R script that writes a standalone `.docx` file. This is architecturally cleaner and avoids all cross-reference risks.

2. **If post-hoc removal is unavoidable**, use `docx_summary()` to enumerate all paragraphs, identify data dictionary paragraphs by content/style, verify none contain bookmarks used by cross-references, then remove them in reverse order (bottom-up) to avoid cursor position shifting.

3. **Validation gate after CSR generation:** Parse the generated `.docx` with `docx_summary()` and verify all bookmarks referenced by `run_reference()` still exist in the document. This is a deterministic check, not LLM-dependent.

**Detection:**
- After generating the CSR, open it and Ctrl+A, F9 (Update Fields) -- broken references show immediately
- Programmatic check: parse the `.docx` XML and verify bookmark IDs match reference field targets

**Phase mapping:** CSR Data Dictionary Removal phase. The recommended approach (modify prompt template, generate separate file) should be the plan -- avoid the `body_remove()` approach entirely.

---

### PITFALL-03: asyncio.gather() Parallelism Broken by Interactive Pause Points

**What goes wrong:** The current orchestrator runs Track A and Track B in parallel via `asyncio.gather()` (line 474 of orchestrator.py). Adding "pause after each step" means inserting an `await` checkpoint inside `_run_track()`. But `_run_track` runs as a gathered coroutine -- if you `await` a user input inside it, you block that track while the other track continues. If you want to pause BOTH tracks between steps, you need synchronization. If you naively add `input()` (synchronous), you block the entire event loop, freezing both tracks, Rich display, and everything else.

**Why it happens:** `input()` is a blocking call. Python's asyncio has no built-in async input. `asyncio.gather()` runs coroutines concurrently in one thread -- blocking one blocks all. The existing `PipelineDisplay` uses `Rich.Live` which continuously refreshes the terminal; calling `input()` during a `Live` display corrupts the terminal output (confirmed by Rich maintainer in GitHub Discussion #1791).

**Consequences:**
- **Blocking the event loop:** `input()` inside an async function freezes all concurrent tasks (both tracks, display refresh, everything)
- **Rich display corruption:** `input()` writes to stdout/stderr, conflicting with Rich's `Live` display which owns the terminal
- **Signal handling:** Ctrl+C during `input()` inside `asyncio.run()` has unpredictable behavior -- may not propagate cleanly
- **Track desynchronization:** If pausing happens inside `_run_track`, Track A and Track B pause at different times (one may be mid-Docker-execution when the other pauses)

**Prevention:**

1. **Pause BETWEEN phases, not inside `_run_track()`:** Interactive mode should insert pause points between the sequential steps in `orchestrator.run()`, not inside the parallel `asyncio.gather()` block. The natural pause points are:
   - After Simulator (before gather)
   - After `asyncio.gather()` returns (both tracks done)
   - After Stage Comparison
   - After Resolution Loop (if triggered)
   - After Medical Writer

   This avoids breaking parallelism entirely. Tracks A and B run together as a unit.

2. **Stop Rich Live before input, restart after:** The pattern is:
   ```python
   display.stop()  # Stop Live rendering
   user_input = await asyncio.get_event_loop().run_in_executor(None, input, "Press Enter to continue...")
   display.start()  # Restart Live rendering
   ```
   This avoids the terminal corruption issue. Rich's `Live.stop()` and `Live.start()` are designed for exactly this use case.

3. **Use `run_in_executor` for input, never raw `input()`:** Wrap `input()` in `loop.run_in_executor(None, input, prompt)` to avoid blocking the event loop. Even though we pause Rich Live, other async cleanup tasks may need to run.

4. **Add `--interactive` CLI flag:** Do not make interactive mode the default. Add a `--interactive` / `-i` flag to the Typer CLI. In non-interactive mode, the pipeline runs exactly as it does today. This prevents accidental breakage of CI/automated runs.

**Detection:**
- Event loop debug mode (`asyncio.run(main(), debug=True)`) detects blocking calls that take >100ms
- Test with `pytest` -- if tests hang waiting for stdin, interactive mode is leaking into non-interactive code paths

**Phase mapping:** Interactive Execution Mode phase. Design the pause points as orchestrator-level (between `await` boundaries in `run()`), not inside `_run_track()`.

---

## Moderate Pitfalls

Mistakes that cause delays, rework, or degraded user experience.

---

### PITFALL-04: LLM Returns Partial Config, Defaults Fill the Gaps Silently

**What goes wrong:** `TrialConfig` has defaults for every field. If the LLM fails to extract `dropout_rate` from the protocol document, the config silently uses `dropout_rate=0.10`. The user never sees that this field was not extracted. If the protocol specifies `dropout_rate=0.25`, the pipeline runs with wrong dropout assumptions.

**Why it happens:** Pydantic defaults are designed for convenience, but in an extraction context they mask missing data. The LLM may return partial JSON (omitting fields it could not find) and Pydantic happily fills in defaults.

**Prevention:**

1. **Separate "extraction schema" from "runtime schema":** Create a `ProtocolExtraction` model where ALL fields are `Optional[T] = None` (no defaults). After extraction, compare against `TrialConfig` fields. Any `None` field must be explicitly confirmed by the user or flagged as "using default."

2. **Extraction completeness report:** After LLM extraction, display:
   ```
   Extracted from protocol:
     n_subjects: 300 (from: "The study enrolled 300 participants...")
     treatment_sbp_mean: 120.0 (from: "Target SBP of 120 mmHg in treatment arm...")

   NOT FOUND in protocol (using defaults):
     dropout_rate: 0.10 (DEFAULT) <-- CONFIRM OR OVERRIDE
     missing_rate: 0.03 (DEFAULT) <-- CONFIRM OR OVERRIDE
   ```

3. **Fail-safe:** If more than 3 fields fall back to defaults, refuse to proceed without explicit user confirmation.

**Detection:**
- Log which fields were explicitly extracted vs defaulted
- Count of defaulted fields > 0 should trigger a warning

**Phase mapping:** Protocol Parser Agent phase. The extraction model is a separate Pydantic class, not `TrialConfig` itself.

---

### PITFALL-05: Word Document Text Extraction Loses Structure

**What goes wrong:** The protocol document (.docx) may contain trial parameters in tables, bulleted lists, headers, or inline with narrative text. Using `python-docx` paragraph iteration (`doc.paragraphs`) only extracts top-level paragraph text -- it misses:
- Values in tables (e.g., "Parameter | Value" tables)
- Values in text boxes or frames
- Numbered list items (list numbering stored in XML, not text)
- Headers/footers

**Why it happens:** Word documents are XML internally. `paragraph.text` extracts the text content but not the structural context. A protocol document might have `n_subjects` in a table row, not a paragraph.

**Prevention:**

1. **Extract ALL text content:** Iterate paragraphs AND tables. For tables, join cell text with structure markers.
   ```python
   full_text = []
   for para in doc.paragraphs:
       full_text.append(para.text)
   for table in doc.tables:
       for row in table.rows:
           row_text = " | ".join(cell.text for cell in row.cells)
           full_text.append(row_text)
   ```

2. **Send the full document text to the LLM** rather than trying to pre-parse structure. The LLM is better at understanding natural language context than brittle regex parsing of document structure.

3. **Consider `mammoth` or `docx2python`** as alternatives to `python-docx` for more complete text extraction including list numbering.

**Detection:**
- If the LLM returns many `None` fields, the document text extraction may have missed the relevant content
- Compare extracted text length to expected document length -- if much shorter, content is being lost

**Phase mapping:** Protocol Parser Agent phase. Text extraction is the first step before LLM call.

---

### PITFALL-06: Data Dictionary Removal Creates Empty Section or Trailing Whitespace

**What goes wrong:** Even with the recommended approach (modifying the prompt template to skip the data dictionary), the LLM-generated R code may still include the data dictionary section on some runs (LLMs do not follow instructions 100% of the time, especially when the existing template has extensive data dictionary code examples). The CSR ends with a blank "Data Dictionary" heading and no content, or trailing empty paragraphs.

**Why it happens:** The medical writer prompt template (`medical_writer.j2`) currently contains 30+ lines of data dictionary R code as an example. Even if you change the instruction to "do not generate a data dictionary," the LLM may still produce one because the example code is in the system prompt. LLMs are strongly influenced by examples in the prompt -- contradicting instructions vs examples, examples usually win.

**Prevention:**

1. **Remove the data dictionary example code entirely from `medical_writer.j2`.** Do not just add "skip the data dictionary" -- physically remove Section 8 from the template. If the LLM never sees the data dictionary code pattern, it will not generate one.

2. **Add a negative instruction:** After removing the example, add: "Do NOT include a data dictionary section. The data dictionary is generated separately."

3. **Post-generation validation:** After the medical writer runs, check the generated `.docx` for a heading containing "Data Dictionary" or "Variable Derivations". If found, either strip it programmatically or re-run with a stronger prompt.

4. **Create a separate `data_dictionary_writer` agent** (or simple template-based R script) that generates the standalone data dictionary `.docx` from `TrialConfig` fields. This is deterministic -- no LLM needed. The data dictionary content is domain knowledge already in the prompt template; it can be a static R script with Jinja2 variable substitution.

**Detection:**
- Parse output `.docx` for "Data Dictionary" heading
- Check word count of last section -- if very short or empty, section stub remained

**Phase mapping:** CSR Data Dictionary Removal phase. Remove from template first, then build standalone generator.

---

### PITFALL-07: Rich Live Display State Not Restored After Interactive Pause

**What goes wrong:** After calling `display.stop()` for an interactive pause and then `display.start()` to resume, the Rich `Live` display loses track of its state. The progress bars reset, step status table shows stale data, and the display flickers or duplicates.

**Why it happens:** `PipelineDisplay.start()` creates a new `Progress` instance and new task IDs (line 151-153 of pipeline_display.py). If you call `stop()` then `start()` mid-pipeline, the new `Progress` has fresh task IDs that don't match the old `_track_a_task` and `_track_b_task` references. Progress advancement calls after restart advance non-existent tasks.

**Prevention:**

1. **Do not create new `Progress` instances on restart.** Refactor `start()` to only create `Progress` on first call. On subsequent calls, just restart the `Live` context:
   ```python
   def start(self):
       if self._progress is None:
           self._progress = self._build_progress()
           self._track_a_task = self._progress.add_task(...)
           self._track_b_task = self._progress.add_task(...)
       if self._interactive:
           from rich.live import Live
           self._live = Live(self._build_renderable(), ...)
           self._live.start()
   ```

2. **Alternative: Do not stop/start Live at all.** Instead of stopping the Live display for input, use `Live.console.input()` (Rich 13+) which handles the coordination automatically. Verify this works with current Rich version.

3. **Test the stop/start cycle explicitly** with a unit test that simulates advancing progress, stopping, restarting, and advancing more.

**Detection:**
- Progress bars show 0/3 after a pause/resume even though steps already completed
- `KeyError` or `InvalidTaskID` errors in Rich's Progress

**Phase mapping:** Interactive Execution Mode phase. Build the display pause/resume mechanism before wiring it into the orchestrator.

---

### PITFALL-08: Protocol Parser Prompt Engineering is Harder Than Expected

**What goes wrong:** Teams underestimate the prompt engineering effort for structured extraction. The first prompt draft works on the example document but fails on edge cases:
- Protocol says "approximately 300" -- LLM extracts 300 but the actual enrollment was 298
- Protocol says "2:1 randomization (Treatment:Placebo)" -- LLM parses as `"2:1"` but the existing config expects this exact string format
- Protocol uses different terminology ("enrolled subjects" vs "participants" vs "sample size") for the same parameter
- Protocol describes the endpoint in prose ("systolic blood pressure reduction below 120 mmHg") and the LLM must map this to `endpoint="SBP"` and `event_threshold=120`

**Why it happens:** Natural language is inherently ambiguous. The `TrialConfig` schema has specific field names and types that do not map 1:1 to how protocols are written.

**Prevention:**

1. **Build a field mapping guide in the prompt:** For each `TrialConfig` field, list synonyms and extraction rules:
   ```
   n_subjects: Look for "sample size", "enrolled", "participants", "subjects".
              Extract the integer. Ignore qualifiers like "approximately".
   dropout_rate: Look for "dropout", "discontinuation", "withdrawal rate".
                 Must be a decimal fraction (0.0-1.0), not a percentage.
                 If "10%", convert to 0.10.
   ```

2. **Test with 3-5 protocol document variants** before considering the feature done. Include:
   - A clean, well-structured protocol
   - A protocol with parameters embedded in prose paragraphs
   - A protocol with parameters in tables
   - A protocol with ambiguous or missing parameters

3. **Version the prompt template** separately from the code. Protocol extraction prompts will need iteration.

**Detection:**
- Extract from same document twice -- if results differ, the prompt is not robust
- Extract from the example protocol and compare to current `config.yaml` values

**Phase mapping:** Protocol Parser Agent phase. Budget 2-3x the expected time for prompt iteration.

---

## Minor Pitfalls

Mistakes that cause annoyance but are fixable without rework.

---

### PITFALL-09: Interactive Mode Breaks CI/Testing Pipeline

**What goes wrong:** After adding interactive mode, `pytest` tests that call `orchestrator.run()` hang waiting for stdin input.

**Prevention:**

1. **Interactive mode is opt-in, never default.** The `--interactive` flag defaults to `False`. The `PipelineOrchestrator.__init__` takes an `interactive: bool = False` parameter.

2. **Callback protocol, not hardcoded input():** Add an `on_step_pause(step_name: str) -> Awaitable[None]` method to `ProgressCallback`. In interactive mode, the display implements this with `input()`. In tests, the mock callback returns immediately. In CI, the callback is a no-op.

3. **Test interactive mode separately** with mocked stdin, not as part of the main test suite.

**Detection:**
- CI timeout on test runs after interactive mode is added
- Tests that worked before now hang

**Phase mapping:** Interactive Execution Mode phase. Define the callback protocol first, implement the input mechanism second.

---

### PITFALL-10: Data Dictionary Standalone File Placed in Wrong Output Directory

**What goes wrong:** The v1.2 requirement says "data dictionary should be written as a standalone file in the relevant output folder (sdtm/adam)." But which folder? SDTM and ADaM each have their own data dictionaries (SDTM variables like DM, VS vs ADaM variables like ADTTE, CNSR). Putting one data dictionary in `sdtm/` and another in `adam/` is correct but requires two separate generation steps. Putting a combined data dictionary in `csr/` alongside the CSR is simpler but does not match the requirement.

**Prevention:**

1. **Clarify the requirement:** The current CSR data dictionary only covers ADTTE variables (Section 8 of the prompt template). So the standalone file goes in the adam output folder (`track_a/adam/` or `track_b/adam/` or both).

2. **Generate per-track:** Since both tracks have their own adam directories, generate the data dictionary in both (or in a shared location). The data dictionary content is deterministic (from `TrialConfig`), so track does not matter.

3. **Name it clearly:** `ADTTE_data_dictionary.docx` not `data_dictionary.docx` to avoid ambiguity.

**Detection:**
- Output directory listing does not include the data dictionary file
- Data dictionary references wrong output location

**Phase mapping:** CSR Data Dictionary Removal phase. Define output path before implementing generation.

---

### PITFALL-11: Keyboard Interrupt During Interactive Pause Leaves Pipeline in Inconsistent State

**What goes wrong:** User presses Ctrl+C during an interactive pause. The `KeyboardInterrupt` propagates through `asyncio.run()` and may leave:
- Docker containers running
- Pipeline state file showing "in progress" for a completed step
- Partial output files

**Prevention:**

1. **Wrap interactive pause in try/except KeyboardInterrupt:** On Ctrl+C during pause, clean up gracefully:
   ```python
   try:
       await loop.run_in_executor(None, input, "Press Enter...")
   except (KeyboardInterrupt, EOFError):
       display.stop()
       # Pipeline state update: "interrupted_by_user"
       state.status = "interrupted"
       state.save(state_path)
       raise
   ```

2. **The existing CLI error handling (cli.py lines 58-65) already catches KeyboardInterrupt** and shows a clean error panel. Ensure the interactive pause propagates correctly to this handler.

3. **EOFError handling:** If stdin is piped (not a terminal), `input()` raises `EOFError`. Treat this the same as pressing Enter (continue without pause). This prevents crashes when someone accidentally runs `--interactive` in a non-TTY environment.

**Detection:**
- Pipeline state file shows "in_progress" but no process is running
- Docker containers orphaned after Ctrl+C

**Phase mapping:** Interactive Execution Mode phase. Handle at the same time as the pause implementation.

---

## Phase-Specific Warnings

| Phase Topic | Likely Pitfall | Severity | Mitigation |
|-------------|---------------|----------|------------|
| Protocol Parser Agent | PITFALL-01: Silent number misextraction | CRITICAL | Multi-layer validation: Pydantic bounds, source citations, human confirmation |
| Protocol Parser Agent | PITFALL-04: Defaults fill gaps silently | MODERATE | Separate extraction schema with `Optional` fields, completeness report |
| Protocol Parser Agent | PITFALL-05: Word text extraction loses tables | MODERATE | Extract both paragraphs and tables from .docx |
| Protocol Parser Agent | PITFALL-08: Prompt engineering underestimated | MODERATE | Budget 2-3x time, test with variant documents |
| CSR Data Dictionary Removal | PITFALL-02: Orphaned cross-references | CRITICAL | Modify prompt template (remove Section 8), do not use body_remove() |
| CSR Data Dictionary Removal | PITFALL-06: LLM still generates data dictionary | MODERATE | Remove example code from template, add negative instruction |
| CSR Data Dictionary Removal | PITFALL-10: Wrong output directory for standalone file | MINOR | Clarify requirement, use adam/ directory |
| Interactive Execution Mode | PITFALL-03: asyncio.gather() broken by input() | CRITICAL | Pause between phases (in run()), not inside _run_track() |
| Interactive Execution Mode | PITFALL-07: Rich Live state lost after pause | MODERATE | Refactor start() to preserve Progress instances |
| Interactive Execution Mode | PITFALL-09: CI/tests hang waiting for stdin | MINOR | Opt-in flag, callback protocol |
| Interactive Execution Mode | PITFALL-11: Ctrl+C during pause leaves mess | MINOR | Graceful interrupt handling, EOFError fallback |

---

## Architectural Recommendation

The three v1.2 features have different risk profiles:

1. **Protocol Parser** is the highest-risk feature because its failure mode is *silent wrong output* in a regulated context. Invest heavily in validation layers. This is not a "parse then validate" problem -- it is a "validate as you parse, validate after you parse, and validate with the user" problem.

2. **CSR Data Dictionary Removal** is the lowest-risk feature IF implemented correctly (modify the prompt template, not the generated document). The anti-pattern (post-hoc document modification with `body_remove()`) is high-risk. Choose the right approach and this becomes trivial.

3. **Interactive Execution Mode** is moderate-risk. The asyncio/Rich interaction has sharp edges, but the solution space is well-understood: pause between sequential phases, not inside parallel blocks; stop/start Rich Live around input; use `run_in_executor` for non-blocking input.

**Suggested phase ordering based on risk:**
1. CSR Data Dictionary Removal first (low risk, quick win, builds confidence)
2. Interactive Execution Mode second (moderate risk, enables step-by-step validation for protocol parser testing)
3. Protocol Parser Agent last (highest risk, benefits from interactive mode for human-in-the-loop validation)

---

## Sources

### LLM Number Extraction
- [Automatically Extracting Numerical Results from RCTs with LLMs](https://arxiv.org/html/2405.01686v2) -- GPT-4 achieves 49-66% exact match on continuous outcomes
- [Clinical Information Extraction with LLMs](https://pmc.ncbi.nlm.nih.gov/articles/PMC12099322/) -- hallucination heuristics increase precision to >95%
- [Challenges in Structured Document Data Extraction at Scale](https://zilliz.com/blog/challenges-in-structured-document-data-extraction-at-scale-llms)
- [Number Cookbook: Number Understanding of Language Models](https://arxiv.org/html/2411.03766v1) -- accuracy drops below 20% for uncommon representations
- [Accuracy and Hallucination of LLMs Analyzing Clinical Notes](https://jamanetwork.com/journals/jamanetworkopen/fullarticle/2822301)

### asyncio and Rich
- [Python asyncio: Event Loop Blocking](https://docs.python.org/3/library/asyncio-dev.html) -- official guidance on blocking calls
- [Rich GitHub Discussion #1791: Input during Live Display](https://github.com/Textualize/rich/discussions/1791) -- confirmed not natively supported
- [Rich Live Display Documentation](https://rich.readthedocs.io/en/stable/live.html) -- stop/start, transient mode
- [asyncio.Event for pause/resume](https://github.com/m2-farzan/asyncio-pause-resume) -- pattern reference
- [Python asyncio Event Loop: connect_read_pipe](https://docs.python.org/3/library/asyncio-eventloop.html) -- async stdin reading

### R officer Package
- [officer body_remove() documentation](https://davidgohel.github.io/officer/reference/body_remove.html) -- one element at a time
- [officer Issue #68: Remove multiple paragraphs](https://github.com/davidgohel/officer/issues/68) -- loop+bookmark workaround
- [Officeverse: officer for Word](https://ardata-fr.github.io/officeverse/officer-for-word.html) -- cursor, bookmark, section handling
- [Word cross-reference troubleshooting](https://www.thedoctools.com/word-macros-tips/word-tips/cross-reference-problems-troubleshooting/) -- orphaned reference behavior

### Pydantic Validation for LLM Outputs
- [Pydantic for LLMs: Schema, Validation & Prompts](https://pydantic.dev/articles/llm-intro)
- [Instructor: Structured LLM Outputs with Validation](https://python.useinstructor.com/)

---
*Researched: 2026-02-14*
*Codebase files reviewed: orchestrator.py, pipeline_display.py, medical_writer.py, config.py, cli.py, retry.py, callbacks.py, error_display.py, medical_writer.j2*
