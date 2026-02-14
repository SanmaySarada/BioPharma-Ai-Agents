# Feature Landscape

**Domain:** Multi-LLM clinical trial pipeline -- v1.2 usability features
**Researched:** 2026-02-14
**Confidence:** MEDIUM-HIGH (feature patterns well-understood; implementation specifics verified against codebase)

---

## Context: What v1.2 Adds

The pipeline already works end-to-end: Simulator -> SDTM -> ADaM -> Stats (dual-track) -> Comparison -> Resolution -> Medical Writer -> CSR. Three new features target usability: (1) protocol parsing from natural language, (2) CSR data dictionary extraction, (3) interactive step-by-step execution mode.

---

## Feature 1: Protocol Parser Agent

### What It Is

A new agent that reads a Word document (.docx) containing a natural-language clinical trial description and extracts structured parameters into the existing `TrialConfig` Pydantic model. The user writes prose like "300 subjects randomized 2:1 with baseline SBP of 150..." and the agent produces `n_subjects=300, randomization_ratio="2:1", baseline_sbp_mean=150.0`, etc.

### Category: Differentiator

This is NOT table stakes -- the pipeline already works with YAML config. Protocol parsing is a workflow convenience that eliminates a manual translation step. Users currently hand-copy numbers from a protocol document into config.yaml. The parser automates that translation.

However, this is a genuine differentiator because:
- It aligns with the clinical trial industry's actual workflow (protocols are Word documents, not YAML files)
- Research shows LLMs achieve ~95% accuracy on clinical data extraction tasks (confirmed by multiple 2025 studies benchmarking GPT-4, Gemini, Claude on ClinicalTrials.gov records)
- No competing open-source clinical trial simulation pipeline offers natural-language protocol ingestion

### How Similar Systems Handle This

**Pattern A: LLM Structured Extraction (Recommended)**

The dominant pattern in 2025-2026 is to use LLMs with structured output schemas. The pipeline:
1. Extract raw text from .docx (using python-docx, already a project dependency)
2. Send text to an LLM with a Pydantic schema describing expected fields
3. LLM returns JSON matching the schema
4. Validate with Pydantic

Tools for this pattern:
- **Instructor** (3M+ monthly downloads, 11k stars): Wraps LLM calls with Pydantic response_model parameter. Handles validation, retries, and type coercion automatically. Works with both OpenAI and Gemini.
- **Native structured output**: Both OpenAI (response_format) and Gemini (response_schema) support JSON schema-constrained generation natively.
- **Direct Pydantic + prompt**: Simply include the JSON schema in the prompt and parse the response. This is what the existing pipeline architecture suggests -- the agents already use Jinja2 prompts and LLM calls.

**Pattern B: NLP Pipeline (Not Recommended)**

Traditional NLP approaches (BiLSTM-CRF, spaCy NER) require training data and are less flexible. The existing system already has LLM infrastructure. Adding a separate NLP pipeline would be over-engineering.

**Pattern C: Template + Regex (Not Recommended)**

Some systems use structured templates with fill-in-the-blank fields. This defeats the purpose -- if the user has to fill a template, they might as well edit YAML.

### Complexity: Medium

| Sub-task | Effort | Notes |
|----------|--------|-------|
| Read .docx text extraction | Low | python-docx already in dependencies |
| Design extraction prompt | Medium | Must handle varied prose styles reliably |
| LLM call + Pydantic validation | Low | Existing infrastructure (BaseLLM, TrialConfig) |
| Validation + user confirmation | Medium | Must show extracted values for human review |
| CLI integration (new command or flag) | Low | Typer already configured |
| Error handling for ambiguous/missing params | Medium | What if the doc omits age_sd? Defaults? Prompt user? |

### Key Design Decisions

1. **Reuse existing LLM infrastructure vs. add Instructor dependency?**
   Recommendation: Reuse existing infrastructure. The project already has `BaseLLM` with Gemini and OpenAI adapters. Adding Instructor would create a third way to call LLMs. Instead, use the existing adapter with a structured prompt that requests JSON output matching `TrialConfig` fields. Use `TrialConfig.model_validate()` for parsing.

2. **Which LLM for extraction?**
   Recommendation: Gemini (already the primary LLM). Text extraction is a single-shot task, not adversarial double programming. No need for dual-track here.

3. **New CLI command or flag on existing `run` command?**
   Recommendation: New `parse-protocol` subcommand that outputs a config.yaml. This separates concerns: parsing is a prep step, not a pipeline execution step. The user runs `omni-agents parse-protocol protocol.docx -o config.yaml` then reviews/edits, then runs `omni-agents run -c config.yaml`.

4. **How to handle missing/ambiguous parameters?**
   Recommendation: Use TrialConfig defaults for unspecified fields. Display ALL extracted values (with source quotes from the document) so the user can verify. Flag any field that fell back to a default.

### Dependencies

- None on other v1.2 features (can be built independently)
- Depends on: python-docx (already installed), existing LLM adapters, TrialConfig model

---

## Feature 2: CSR Data Dictionary Cleanup

### What It Is

Currently, the Medical Writer agent generates a Clinical Study Report that includes a data dictionary section (Section 8 in the template) defining ADTTE variable derivations. The user wants this data dictionary moved OUT of the CSR and INTO standalone files placed in the sdtm/ and adam/ output directories alongside the data files they describe.

### Category: Table Stakes (for regulatory correctness)

In the CDISC ecosystem, metadata about datasets is supposed to travel WITH the datasets, not buried inside a narrative report. The industry standard is Define-XML -- an XML file co-located with SDTM/ADaM datasets that describes every variable, its derivation, controlled terminology, and data type. The CSR is a narrative document for humans; the data dictionary is metadata for programmatic consumption.

Having the data dictionary inside the CSR is an anti-pattern because:
- Regulatory reviewers expect metadata alongside data files, not embedded in the report
- Define-XML (required by FDA and PMDA) is a standalone file, not a section of a Word doc
- It makes the CSR longer without adding narrative value
- It cannot be machine-read when embedded in a .docx

### How Similar Systems Handle This

**Pattern A: Define-XML (Industry Standard, Overkill Here)**

Real regulatory submissions use Define-XML v2.0 -- a formal XML schema describing all datasets and variables. This is the gold standard but is extremely complex to generate and irrelevant for a simulation pipeline that produces CSV files (not SAS XPT).

Recommendation: Do NOT implement Define-XML. It is disproportionate complexity for this project's scope.

**Pattern B: CSV Data Dictionary (Recommended)**

Generate a CSV file with columns: Variable, Label, Type, Derivation, ControlledTerminology. Place one in `sdtm/` (describing DM.csv and VS.csv variables) and one in `adam/` (describing ADTTE variables). This is:
- Machine-readable (CSV, same as the data files)
- Human-readable (open in Excel or any text editor)
- Co-located with the data it describes
- Simple to generate (the content already exists in the medical_writer.j2 template)

**Pattern C: JSON Metadata Sidecar (Alternative)**

Similar to Pattern B but as JSON. The ADaM agent already generates `ADTTE_summary.json` as a validation sidecar. A data dictionary JSON would be consistent with this pattern.

Recommendation: Use CSV for the data dictionary files (consistent with the CSV data outputs) and keep the existing ADTTE_summary.json for validation metadata. Two separate concerns.

### Complexity: Low

| Sub-task | Effort | Notes |
|----------|--------|-------|
| Remove Section 8 from medical_writer.j2 | Low | Delete ~35 lines from prompt template |
| Generate SDTM data_dictionary.csv | Low | Static content, can be written by SDTM agent or orchestrator |
| Generate ADaM data_dictionary.csv | Low | Static content, can be written by ADaM agent or orchestrator |
| Update schema validator to check for dictionary files | Low | Optional but good practice |
| Update README output structure | Low | Documentation |

### Key Design Decisions

1. **Who generates the data dictionary files -- the LLM agents or the orchestrator?**
   Recommendation: The orchestrator writes them deterministically. Data dictionary content is static domain knowledge (variable names, labels, derivation rules). It does not need LLM generation -- the content is identical for every run. Hardcoding it in Python avoids LLM variability and saves an API call.

2. **One file per domain or one combined file?**
   Recommendation: One per domain -- `sdtm/data_dictionary.csv` and `adam/data_dictionary.csv`. Each describes only the variables in its sibling data files. This follows the CDISC principle of metadata traveling with its data.

3. **CSV or JSON format?**
   Recommendation: CSV. The data files are CSV. The data dictionary describes CSV columns. Using CSV maintains format consistency. Columns: Variable, Label, Type, Derivation, ControlledTerminology (where applicable).

### Dependencies

- Depends on: Medical Writer prompt template (medical_writer.j2), orchestrator output paths
- Must coordinate with: SDTM and ADaM agent output directories (already exist)
- Independent from: Protocol parser and interactive mode

---

## Feature 3: Interactive Execution Mode

### What It Is

Currently the pipeline runs all 9 steps autonomously (Simulator -> SDTM_A, SDTM_B -> ADaM_A, ADaM_B -> Stats_A, Stats_B -> Comparison -> Medical Writer). The user wants an option to pause after each step completes, display a summary, and wait for Enter before proceeding to the next step.

### Category: Table Stakes (for development and review workflows)

Step-by-step execution is table stakes for any multi-stage pipeline that produces intermediate outputs:
- Users need to inspect SDTM outputs before ADaM runs
- Users need to verify simulator data looks reasonable before committing to a 2-minute dual-track analysis
- Debugging a failing step requires isolating it without running the whole pipeline
- Regulatory review workflows often require sign-off between stages

### How Similar Systems Handle This

**Pattern A: CLI Flag for Execution Mode (Recommended)**

Most pipeline tools (Jenkins, Tekton, Airflow) support both autonomous and interactive modes via configuration:
- `--interactive` / `--step` flag on the CLI command
- Pipeline pauses after each step, displays results summary, waits for user input
- User presses Enter to continue or Ctrl+C to abort

This is the simplest and most user-friendly pattern. No state persistence needed -- it is a runtime behavior flag.

**Pattern B: Breakpoints / Interrupt Functions (LangGraph Pattern)**

LangGraph uses `interrupt()` calls that pause execution and persist state to a checkpoint. This enables resuming from a different process or after a restart. It is powerful but requires a persistence layer (SQLite, Redis, etc.).

Recommendation: Overkill for this project. The pipeline runs in a single CLI session. Simple stdin wait is sufficient.

**Pattern C: DAG Scheduler with Step Selection**

Some systems let users select which steps to run (e.g., `--steps sdtm,adam`). This is more flexible but more complex.

Recommendation: Defer step selection to a future version. Interactive mode (pause between all steps) covers the immediate need.

### Complexity: Medium

| Sub-task | Effort | Notes |
|----------|--------|-------|
| Add `--interactive` flag to CLI | Low | Typer option, passed to orchestrator |
| Implement pause mechanism in orchestrator | Medium | asyncio + blocking input interaction |
| Display step summary before pause | Medium | What to show: output file list, row counts, validation status |
| Handle parallel track execution in interactive mode | Medium | Do you pause between SDTM_A and SDTM_B, or after both? |
| Update PipelineDisplay for interactive prompts | Medium | Must work with Rich Live display |
| Test both modes don't regress | Low | Existing test suite + new flag tests |

### Key Design Decisions

1. **Where does the pause happen -- between stages or between individual steps?**

   Recommendation: Pause between STAGES, not individual steps. The pipeline has 5 logical stages:
   1. Simulation (Simulator)
   2. Analysis (SDTM + ADaM + Stats, both tracks in parallel)
   3. Comparison (StageComparator)
   4. Resolution (if needed)
   5. Reporting (Medical Writer)

   Pausing between every one of the 9 individual steps would be tedious and would break the parallel track execution model. Instead, pause between the 5 logical stages. Within Stage 2, both tracks run in parallel as normal. The user sees: "Simulation complete. Press Enter to start parallel analysis..." then "Both tracks complete. Press Enter for comparison..." etc.

   HOWEVER, consider an alternative: pause between sub-stages within the parallel analysis too. Since each track runs SDTM->ADaM->Stats sequentially, you COULD pause after both SDTMs complete, then after both ADaMs, then after both Stats. This gives finer-grained review at the cost of more pauses (7 pauses instead of 4).

   Recommendation: Start with stage-level pauses (4-5 pauses per run). If users want finer granularity, add `--interactive=verbose` later.

2. **How to handle asyncio + blocking input()?**

   The pipeline is async. `input()` is blocking and would freeze the event loop. The standard solution is `asyncio.get_event_loop().run_in_executor(None, input, "Press Enter to continue...")`. This runs `input()` in a thread pool without blocking the event loop.

3. **How does this interact with the Rich Live display?**

   The Rich Live display (`PipelineDisplay`) renders a status table with a `Live` context. Calling `input()` while `Live` is active will corrupt the terminal. The pause must:
   - Stop the Live display temporarily
   - Print the step summary
   - Wait for input
   - Restart the Live display

   This is the trickiest implementation detail. The `PipelineDisplay` already has `start()` and `stop()` methods, so this is feasible.

4. **What to display at each pause point?**

   Recommendation: Show a Rich Panel with:
   - Step name and status (completed successfully, N attempts)
   - Key metrics (row counts, file sizes, validation results)
   - Output file paths
   - "Press Enter to continue or Ctrl+C to abort"

### Dependencies

- Depends on: CLI (Typer), orchestrator.run(), PipelineDisplay
- Must coordinate with: Rich Live display start/stop lifecycle
- Independent from: Protocol parser and CSR cleanup

---

## Table Stakes Summary

Features users expect. Missing these makes the product feel incomplete FOR ITS TARGET USERS (developers reviewing pipeline output step-by-step, and clinical researchers providing protocol documents).

| Feature | Why Expected | Complexity | Phase Priority |
|---------|--------------|------------|----------------|
| Interactive execution mode | Every multi-stage pipeline needs a debug/review mode | Medium | High -- most immediately useful |
| CSR data dictionary extraction | Metadata belongs with data, not in narrative reports | Low | High -- small change, big correctness win |
| Protocol parser (basic) | Users should not hand-translate prose to YAML | Medium | Medium -- convenience, not correctness |

## Differentiators Summary

Features that set the product apart. Not expected, but valued.

| Feature | Value Proposition | Complexity | Phase Priority |
|---------|-------------------|------------|----------------|
| Protocol parser with source quoting | Shows which part of the document each parameter came from | Medium | Medium |
| Interactive mode with output previews | Shows data summaries (not just "step done") at each pause | Medium | Low (enhancement) |
| Data dictionary in both CSV and JSON | Machine-readable metadata in two formats | Low | Low (enhancement) |

## Anti-Features Summary

Features to explicitly NOT build for v1.2.

| Anti-Feature | Why Avoid | What to Do Instead |
|--------------|-----------|-------------------|
| Define-XML generation | Disproportionate complexity for a simulation pipeline. Real Define-XML requires controlled terminology mapping, origin tracking, and value-level metadata. | Simple CSV data dictionary |
| Protocol parser with interactive Q&A | Tempting to build a chatbot that asks "I found n_subjects=300, is that right?" But this adds conversational state management complexity for minimal gain. | Extract all at once, show results, let user edit config.yaml |
| Step selection (`--steps sdtm,adam`) | Requires tracking which steps have cached outputs, dependency resolution, and partial pipeline state. | Full pipeline with optional pauses between stages |
| Protocol parser that edits config.yaml in-place | Merging LLM output into an existing YAML file risks corrupting user comments and formatting. | Write a fresh config.yaml (or print to stdout) |
| Dual-LLM protocol parsing | Using both Gemini and GPT-4 to parse the protocol and comparing results is technically possible but unnecessary. Protocol parsing is deterministic text extraction, not statistical analysis. | Single-LLM extraction with user verification |
| Interactive mode with rollback | "Go back to step 3 and re-run from there" requires checkpoint/restore infrastructure. | Forward-only execution; if something went wrong, re-run the whole pipeline |
| Auto-detection of protocol file format | Supporting .docx, .pdf, .txt, .rtf, etc. | Support .docx only (industry standard for protocols). Convert other formats externally. |

---

## Feature Dependencies

```
Protocol Parser ──────> config.yaml ──────> Pipeline Execution
(independent)           (existing)          (existing)

CSR Cleanup ──────> Medical Writer Template + Orchestrator
(independent)       (modify existing)

Interactive Mode ──────> Orchestrator + CLI + Display
(independent)            (modify existing)

No cross-dependencies between the three features.
All three can be built in parallel or any order.
```

### Dependency Detail

| Feature | Reads From | Writes To | Modifies |
|---------|-----------|----------|----------|
| Protocol Parser | .docx file (user input) | config.yaml (new file) | cli.py (new subcommand), new agent class |
| CSR Cleanup | medical_writer.j2 template | sdtm/data_dictionary.csv, adam/data_dictionary.csv | medical_writer.j2, orchestrator.py |
| Interactive Mode | CLI flags | stdout (pause prompts) | cli.py, orchestrator.py, pipeline_display.py |

---

## MVP Recommendation

For v1.2 MVP, prioritize in this order:

1. **CSR Data Dictionary Cleanup** (Low complexity, high correctness value)
   - Smallest change, biggest impact on output quality
   - Removes an anti-pattern from the current CSR
   - Can be done in a single plan

2. **Interactive Execution Mode** (Medium complexity, high usability value)
   - Most immediately useful for development and review workflows
   - The pipeline is already reliable (v1.1 fixed error handling); now users need to inspect outputs
   - Requires coordinating CLI, orchestrator, and display -- more moving parts

3. **Protocol Parser Agent** (Medium complexity, medium immediate value)
   - Nice-to-have convenience feature
   - Requires careful prompt engineering and testing with varied protocol prose styles
   - Should be done last because it is the most likely to need iteration

### Defer to Post-v1.2

- Step-level pauses within parallel tracks (enhancement to interactive mode)
- Protocol parser with source quoting (enhancement to parser)
- Define-XML generation (unnecessary complexity)
- Step selection / partial pipeline runs (requires checkpoint infrastructure)

---

## Sources

### Protocol Parsing
- [Benchmarking Multiple LLMs for Automated Clinical Trial Data Extraction](https://www.mdpi.com/1999-4893/18/5/296) -- 2025 benchmark of 5 LLMs on protocol extraction (MEDIUM confidence)
- [LLM-Powered Parsing of Semi-Structured Documents](https://towardsdatascience.com/llm-powered-parsing-and-analysis-of-semi-structured-structured-documents-f03ac92f063e/) -- Patterns for .docx extraction pipelines (MEDIUM confidence)
- [Instructor Library](https://python.useinstructor.com/) -- 3M+ downloads, structured output from LLMs with Pydantic (HIGH confidence, official docs)
- [Pydantic for LLMs](https://pydantic.dev/articles/llm-intro) -- Official Pydantic guide for LLM schema generation (HIGH confidence)
- [Clinical Trials Protocol Authoring using LLMs](https://arxiv.org/html/2404.05044v1) -- Research on GPT-4 for protocol generation/parsing (MEDIUM confidence)

### Data Dictionary / CDISC Metadata
- [CDISC Define-XML Standard](https://www.cdisc.org/standards/data-exchange/define-xml) -- Official CDISC metadata standard (HIGH confidence)
- [ADaM Standards](https://www.cdisc.org/standards/foundational/adam) -- ADaM requires metadata via Define-XML (HIGH confidence)
- [CDISC SDTM and ADaM Guide](https://intuitionlabs.ai/articles/cdisc-sdtm-adam-guide) -- Practical guide to metadata delivery (MEDIUM confidence)

### Interactive Pipeline Execution
- [LangGraph Interrupts](https://docs.langchain.com/oss/python/langgraph/interrupts) -- Human-in-the-loop interrupt pattern (HIGH confidence, official docs)
- [Tekton Pipeline Interactive Mode](https://github.com/tektoncd/pipeline/discussions/4134) -- Pipeline pause/resume patterns (MEDIUM confidence)
- [Python asyncio Synchronization Primitives](https://docs.python.org/3/library/asyncio-sync.html) -- asyncio.Event for pause/resume (HIGH confidence, official docs)

### Verified Against Codebase
- `config.py` -- TrialConfig Pydantic model (14 fields to extract)
- `medical_writer.j2` -- Section 8 data dictionary currently in CSR template (lines 173-211)
- `orchestrator.py` -- Pipeline execution flow, `_run_agent()` and `run()` methods
- `cli.py` -- Typer CLI with single `run` command
- `pipeline_display.py` -- Rich Live display with start/stop lifecycle
- `pyproject.toml` -- python-docx already a dependency
