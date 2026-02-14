# Architecture Patterns: v1.2 Feature Integration

**Domain:** Multi-LLM clinical trial pipeline (Python + R in Docker)
**Researched:** 2026-02-14
**Overall confidence:** HIGH (based on direct codebase analysis)

## Current Architecture Snapshot

```
CLI (Typer)
  |
  v
Settings.from_yaml(config.yaml) --> Settings { trial: TrialConfig, llm, docker, resolution }
  |
  v
PipelineOrchestrator.__init__(settings, callback, console)
  |
  v
orchestrator.run()
  |-- Simulator (sequential, shared)
  |-- asyncio.gather(
  |       _run_track("track_a", gemini, ...),
  |       _run_track("track_b", openai, ...)
  |   )
  |   Each track: SDTM --> ADaM --> Stats (sequential within track)
  |-- StageComparator.compare_all_stages()
  |-- ResolutionLoop.resolve() (if disagreement)
  |-- MedicalWriterAgent (generates CSR .docx)
  v
output/<run_id>/
```

Key structural facts from the codebase:

1. **BaseAgent** is stateless: receives context dict, calls LLM, returns R code string. Orchestrator owns execution (Docker), retry, state.
2. **All agents produce R code** that runs in Docker. Even the MedicalWriterAgent generates R code using the `officer` package to create a Word doc.
3. **TrialConfig** is a flat Pydantic model with 17 numeric/string fields. Every agent receives it at `__init__` and extracts template variables from it.
4. **Prompt templates** are Jinja2 `.j2` files loaded by `BaseAgent.load_system_prompt()`. Template variables come from `get_system_prompt_vars()` on each agent subclass.
5. **ProgressCallback** is a Protocol with 9 methods. `PipelineDisplay` implements it. The orchestrator calls `self.callback.on_step_start/complete/fail/retry` throughout `run()`.
6. **PipelineState** tracks step-level results in a dict and persists to `pipeline_state.json`.

---

## Feature 1: Protocol Parser Agent

### What It Does

Reads a `.docx` protocol document (natural-language trial description), calls an LLM to extract structured parameters, and produces a `TrialConfig` Pydantic object. This replaces the manual YAML authoring step.

### Where It Lives in the Architecture

The protocol parser runs BEFORE the pipeline -- it is a **config-generation step**, not a pipeline step. It does not produce R code, does not run in Docker, and does not participate in the retry/execution loop.

```
CLI (Typer)
  |
  |-- IF --protocol flag:
  |     ProtocolParserAgent.parse(protocol.docx) --> TrialConfig
  |   ELSE:
  |     Settings.from_yaml(config.yaml) --> TrialConfig
  |
  v
PipelineOrchestrator(settings)
```

### Recommended Component: `ProtocolParserAgent`

**Location:** `src/omni_agents/agents/protocol_parser.py`

**Why NOT a BaseAgent subclass:** BaseAgent is designed for the generate-R-code-then-execute-in-Docker pattern. The protocol parser needs to:
- Read a `.docx` file with `python-docx` (Python-side, not R)
- Call an LLM with the document text as context
- Parse structured JSON output from the LLM response
- Validate and return a `TrialConfig` Pydantic model

None of these steps involve R code generation or Docker execution. Forcing it into BaseAgent would require either (a) no-op overrides for `inject_seed`, `prompt_template_name`, etc., or (b) extracting an even-more-abstract base class. Both add complexity for no gain.

**Recommended pattern:** Standalone class, not inheriting from BaseAgent.

```python
class ProtocolParserAgent:
    """Parses a clinical trial protocol document into a TrialConfig.

    Not a BaseAgent subclass -- this agent produces structured data,
    not R code. It runs in-process (no Docker) and is invoked before
    the pipeline starts.
    """

    def __init__(self, llm: BaseLLM, prompt_dir: Path) -> None:
        self.llm = llm
        self.prompt_dir = prompt_dir

    async def parse(self, protocol_path: Path) -> TrialConfig:
        """Extract trial parameters from a .docx protocol document.

        1. Read .docx with python-docx, extract full text
        2. Load system prompt from protocol_parser.j2
        3. Call LLM with system prompt + document text
        4. Parse JSON from LLM response
        5. Validate against TrialConfig schema
        6. Return TrialConfig
        """
        ...
```

### Data Flow

```
protocol.docx
  |
  v (python-docx: extract text)
raw_text: str
  |
  v (LLM call: system prompt instructs JSON output)
json_str: str
  |
  v (json.loads + TrialConfig.model_validate)
TrialConfig
  |
  v (injected into Settings, replacing Settings.trial)
Settings
  |
  v
PipelineOrchestrator (existing flow continues unchanged)
```

### Integration Points

**1. CLI layer (`cli.py`)**

Add a `--protocol` option to the `run` command. When provided, it triggers the parser before constructing the orchestrator:

```python
@app.command()
def run(
    config: Path = _config_option,
    protocol: Path | None = typer.Option(None, "--protocol", "-p",
        help="Path to .docx protocol document (overrides trial config in YAML)"),
) -> None:
    settings = Settings.from_yaml(config)

    if protocol is not None:
        parser = ProtocolParserAgent(llm=GeminiAdapter(settings.llm.gemini), ...)
        trial_config = asyncio.run(parser.parse(protocol))
        settings = settings.model_copy(update={"trial": trial_config})

    orchestrator = PipelineOrchestrator(settings, ...)
    asyncio.run(orchestrator.run())
```

**2. Settings model (`config.py`)**

No structural change needed to `TrialConfig` or `Settings`. The parser produces a `TrialConfig` that replaces `settings.trial`. All downstream code consumes `settings.trial` as before.

**3. Prompt template**

New file: `src/omni_agents/templates/prompts/protocol_parser.j2`

This template instructs the LLM to extract specific fields matching `TrialConfig` field names, output as JSON, and handle missing fields with sensible defaults. The template should enumerate all 17 TrialConfig fields with descriptions.

**4. LLM response parsing**

The protocol parser needs a dedicated response parser (not `extract_r_code` from `llm/response_parser.py`). It should extract JSON from the LLM response (look for ```json fenced blocks or raw JSON).

New function: `extract_json(raw_text: str) -> dict` in `llm/response_parser.py`.

### Component Boundary Rules

| Boundary | Rule |
|----------|------|
| Protocol Parser --> TrialConfig | Parser ONLY produces TrialConfig. It does not know about Settings, Docker, or the pipeline. |
| CLI --> Protocol Parser | CLI owns the decision of whether to use the parser (--protocol flag). |
| Protocol Parser --> LLM | Uses the same BaseLLM interface as all agents. No special LLM adapter. |
| TrialConfig --> Pipeline | TrialConfig is the ONLY interface. The pipeline never sees the protocol document. |

### Build Order Dependencies

1. `extract_json()` response parser (no dependencies)
2. `protocol_parser.j2` prompt template (no dependencies)
3. `ProtocolParserAgent` class (depends on 1, 2)
4. CLI integration (depends on 3)

---

## Feature 2: CSR Data Dictionary Extraction

### What It Does

The data dictionary (ADTTE variable descriptions) is currently embedded in the CSR Word document as Section 8 (lines 172-211 of `medical_writer.j2`). It needs to be:
1. Removed from the CSR Word doc
2. Written as a standalone file by the ADaM agent or a post-processing step

### Architecture Decision: Who Writes the Data Dictionary?

**Option A: ADaM agent writes it** -- The ADaM agent already creates ADTTE.rds and ADTTE_summary.json. It could also write a `data_dictionary.csv` alongside them.

**Option B: Post-processing step in orchestrator** -- A new step after ADaM that generates the file from TrialConfig parameters.

**Option C: Python-side (no LLM, no Docker)** -- The data dictionary is static domain knowledge parameterized only by `event_threshold` from TrialConfig. Generate it deterministically in Python.

**Recommendation: Option C** -- The data dictionary content is fully deterministic. It contains fixed CDISC variable definitions with one parameterized value (`event_threshold`). There is zero reason to involve an LLM or Docker container for this. A Python function that takes `TrialConfig` and writes a CSV/JSON file is simpler, faster, and guaranteed correct.

### Where It Lives

```
Orchestrator.run()
  |
  |-- [after ADaM stage completes for each track]
  |     write_data_dictionary(adam_dir, trial_config)
  |
  |-- [MedicalWriterAgent: Section 8 removed from template]
```

### Recommended Component: `write_data_dictionary()`

**Location:** `src/omni_agents/pipeline/data_dictionary.py`

```python
def write_data_dictionary(output_dir: Path, trial_config: TrialConfig) -> Path:
    """Write the ADTTE data dictionary as a standalone CSV file.

    This is deterministic domain knowledge -- no LLM needed.
    Parameterized only by event_threshold derived from trial config.

    Returns:
        Path to the written data_dictionary.csv file.
    """
    ...
```

### Integration Points

**1. Orchestrator (`orchestrator.py`)**

Call `write_data_dictionary()` after each track's ADaM step completes, inside `_run_track()`:

```python
# After ADaM validation passes:
from omni_agents.pipeline.data_dictionary import write_data_dictionary
write_data_dictionary(adam_dir, self.settings.trial)
```

This is a synchronous Python call (no async needed -- it just writes a file). It runs inside the existing track flow, so both Track A and Track B get their own copy in their respective adam directories.

**2. Medical Writer template (`medical_writer.j2`)**

Remove Section 8 (lines 172-211). The section heading "Data Dictionary: ADTTE Variable Derivations" and the `dict_data` dataframe construction are deleted entirely. Also remove Critical Rule 6 ("DATA DICTIONARY (CSR-04)").

**3. Medical Writer agent (`medical_writer.py`)**

No code changes needed in the Python agent class. The system prompt template change handles everything.

### Data Flow

```
TrialConfig.event_threshold (= 120)
  |
  v (write_data_dictionary)
<track_dir>/adam/data_dictionary.csv
  |
  v (standalone output artifact)
No downstream consumer in pipeline -- informational artifact
```

### Component Boundary Rules

| Boundary | Rule |
|----------|------|
| data_dictionary --> filesystem | Writes ONE file: data_dictionary.csv to the specified output dir. |
| data_dictionary --> TrialConfig | Reads only event_threshold (and potentially endpoint name). No other dependencies. |
| orchestrator --> data_dictionary | Orchestrator calls it. The function is pure (no side effects beyond file write). |
| medical_writer.j2 | Section 8 is REMOVED. The template no longer references data dictionary content. |

### Build Order Dependencies

1. `data_dictionary.py` module (no dependencies beyond TrialConfig)
2. Template change to `medical_writer.j2` (independent of step 1)
3. Orchestrator integration (depends on 1)

Steps 1 and 2 can be done in parallel.

---

## Feature 3: Interactive Execution Mode

### What It Does

Adds optional pause points between pipeline steps where the CLI waits for user input (Enter to continue) before proceeding to the next step. The existing autonomous mode remains the default.

### Architecture Analysis: Where Do Pause Points Go?

The current execution flow in `orchestrator.run()` is:

```
1. Simulator           (sequential)
2. Track A + Track B   (asyncio.gather -- parallel)
3. StageComparator     (sequential)
4. ResolutionLoop      (conditional)
5. MedicalWriter       (sequential)
```

The natural pause points are BETWEEN these logical blocks, not between individual agents within a track (pausing mid-`asyncio.gather` is architecturally messy and unintuitive for users). Within a track, the three agents (SDTM -> ADaM -> Stats) are tightly coupled by data dependencies -- pausing between them provides limited value and would require significant refactoring of `_run_track()`.

**Recommended pause points:**

| After | Pause Rationale | User Can Inspect |
|-------|-----------------|------------------|
| Simulator | Review raw data before analysis begins | `raw/SBPdata.csv` |
| Parallel tracks | Review both tracks' outputs before comparison | `track_a/`, `track_b/` |
| StageComparator | Review comparison verdict before resolution/CSR | `consensus/stage_comparisons.json` |
| MedicalWriter | N/A (final step, pipeline done) | N/A |

### Architecture Decision: Where Does the Pause Logic Live?

**Option A: In the orchestrator** -- Add `if self.interactive: await self._pause("After simulator")` calls inline in `run()`.

**Option B: In the callback/display layer** -- Extend `ProgressCallback` with an `on_pause(step_name) -> bool` method. The orchestrator calls `self.callback.on_pause()`, and the display implementation handles the actual `input()` call.

**Option C: Orchestrator-level hook system** -- Add pre/post hooks for each step that the orchestrator calls, with the interactive pause being one hook implementation.

**Recommendation: Option B** -- The pause is a UI concern, not a pipeline logic concern. The orchestrator should not know about `input()`, stdin, or terminal interaction. The `ProgressCallback` protocol already cleanly separates pipeline logic from display, and this extends that pattern naturally.

However, there is a critical constraint: `input()` is a blocking call, and the orchestrator runs in an async context (`asyncio.run()`). The pause must either:
- Use `asyncio.get_event_loop().run_in_executor(None, input)` to avoid blocking the event loop
- Or: the callback itself handles the async/sync bridge

**Recommended approach:** Add an async `on_checkpoint()` method to a new `InteractiveCallback` subclass (not to the Protocol itself, since non-interactive implementations should not need to implement it). The orchestrator checks `isinstance(self.callback, InteractiveCallback)` and awaits the checkpoint call.

### Recommended Architecture

```
CLI (--interactive flag)
  |
  v
InteractivePipelineDisplay(PipelineDisplay)
  |-- overrides on_checkpoint() to prompt user
  |-- uses run_in_executor for blocking input()
  |
  v
PipelineOrchestrator
  |-- calls await self._checkpoint("after_simulator") at pause points
  |-- _checkpoint checks isinstance(callback, InteractiveCallback)
  |-- if not interactive, _checkpoint is a no-op
```

### Integration Points

**1. Callback protocol (`display/callbacks.py`)**

Do NOT modify the existing `ProgressCallback` Protocol -- that would force all implementations to add the method. Instead, define a separate ABC or Protocol:

```python
class InteractiveCallback(ProgressCallback, Protocol):
    """Extended callback that supports interactive pause points."""

    async def on_checkpoint(self, step_name: str, message: str) -> bool:
        """Called at interactive pause points.

        Args:
            step_name: Which step just completed.
            message: Human-readable description of what to inspect.

        Returns:
            True to continue, False to abort pipeline.
        """
        ...
```

**2. Display layer (`display/pipeline_display.py` or new `display/interactive_display.py`)**

```python
class InteractivePipelineDisplay(PipelineDisplay):
    """Pipeline display with interactive pause points."""

    async def on_checkpoint(self, step_name: str, message: str) -> bool:
        self.stop()  # Pause the Live display
        self.console.print(f"\n[bold]Checkpoint:[/bold] {message}")
        self.console.print("[dim]Press Enter to continue, or 'q' to abort...[/dim]")

        loop = asyncio.get_event_loop()
        response = await loop.run_in_executor(None, input)

        if response.strip().lower() == 'q':
            return False

        self.start()  # Resume the Live display
        return True
```

**3. Orchestrator (`orchestrator.py`)**

Add a private helper method and calls at pause points:

```python
async def _checkpoint(self, step_name: str, message: str) -> None:
    """Pause for user confirmation if running in interactive mode."""
    if isinstance(self.callback, InteractiveCallback):
        should_continue = await self.callback.on_checkpoint(step_name, message)
        if not should_continue:
            raise KeyboardInterrupt("User aborted at checkpoint")

async def run(self) -> Path:
    # ... Simulator ...
    await self._checkpoint("after_simulator",
        f"Simulator complete. Inspect raw data at {raw_dir}")

    # ... asyncio.gather (parallel tracks) ...
    await self._checkpoint("after_tracks",
        f"Both tracks complete. Inspect outputs at {output_dir}")

    # ... StageComparator ...
    await self._checkpoint("after_comparison",
        f"Comparison verdict: {verdict.verdict.value}. "
        f"Inspect at {consensus_dir}")

    # ... MedicalWriter ...
```

**4. CLI (`cli.py`)**

```python
@app.command()
def run(
    config: Path = _config_option,
    interactive: bool = typer.Option(False, "--interactive", "-i",
        help="Pause between pipeline steps for manual inspection"),
) -> None:
    settings = Settings.from_yaml(config)

    if interactive:
        display = InteractivePipelineDisplay()
    else:
        display = PipelineDisplay()

    orchestrator = PipelineOrchestrator(settings, callback=display, ...)
```

### Component Boundary Rules

| Boundary | Rule |
|----------|------|
| Orchestrator --> Callback | Orchestrator calls `_checkpoint()`. It never calls `input()` directly. |
| _checkpoint --> InteractiveCallback | Uses `isinstance` check. Non-interactive callbacks are unaffected. |
| InteractivePipelineDisplay --> stdin | Only this class touches `input()`. Uses `run_in_executor` to avoid blocking the event loop. |
| CLI --> Display | CLI decides which display class to instantiate based on `--interactive` flag. |
| ProgressCallback Protocol | NOT modified. Existing implementations remain valid. |

### Rich Live Display Interaction

There is a subtle but critical interaction: Rich's `Live` display owns the terminal while active. Calling `input()` while `Live` is running produces garbled output. The `InteractivePipelineDisplay.on_checkpoint()` method MUST:

1. Call `self.stop()` to suspend the Live display before prompting
2. Print the checkpoint message to the console
3. Wait for input
4. Call `self.start()` to resume the Live display after input

This is the reason `stop()` and `start()` already exist as public methods on `PipelineDisplay` -- they were designed to be called externally (see `cli.py` lines 53-56 where `display.start()` and `display.stop()` bracket the pipeline run).

### Build Order Dependencies

1. `InteractiveCallback` protocol definition (no dependencies)
2. `InteractivePipelineDisplay` class (depends on 1)
3. Orchestrator `_checkpoint()` method + checkpoint calls (depends on 1)
4. CLI `--interactive` flag integration (depends on 2, 3)

Steps 2 and 3 can be done in parallel after step 1.

---

## Cross-Feature Interaction Analysis

### Do the three features interact with each other?

**Protocol Parser x Data Dictionary:** No interaction. The protocol parser produces a TrialConfig. The data dictionary reads from TrialConfig. But there is no direct coupling -- they both use the same TrialConfig interface independently.

**Protocol Parser x Interactive Mode:** Minimal interaction. If `--protocol` is provided alongside `--interactive`, the protocol parsing happens BEFORE the orchestrator starts, so it is outside the interactive checkpoint scope. However, there is a UX consideration: when using `--protocol`, the user may want to review the extracted TrialConfig before the pipeline runs. This could be a checkpoint at the CLI level (not orchestrator level):

```python
if protocol:
    trial_config = asyncio.run(parser.parse(protocol))
    if interactive:
        console.print(trial_config.model_dump_json(indent=2))
        # prompt: "Does this look correct? Enter to continue, q to abort"
    settings = settings.model_copy(update={"trial": trial_config})
```

This is a CLI-level concern and does not affect the orchestrator architecture.

**Data Dictionary x Interactive Mode:** No interaction. The data dictionary write is a non-blocking Python call inside `_run_track()`. It happens within a track, which is within the `asyncio.gather()`, so there is no natural checkpoint boundary for it.

### Shared Infrastructure Changes

| Change | Features Affected | Risk |
|--------|-------------------|------|
| `extract_json()` in response_parser.py | Protocol Parser only | LOW -- additive, no existing code modified |
| `medical_writer.j2` template edit | Data Dictionary only | MEDIUM -- must not break existing CSR generation |
| `ProgressCallback` ecosystem | Interactive Mode only | LOW -- new Protocol, existing one untouched |
| `cli.py` new options | All three | LOW -- additive CLI flags |
| `orchestrator.py` checkpoint calls | Interactive Mode only | LOW -- no-op when callback is not InteractiveCallback |
| `orchestrator.py` data_dictionary call | Data Dictionary only | LOW -- one line addition in _run_track |

---

## Recommended Component Map (After v1.2)

```
src/omni_agents/
  agents/
    base.py              (unchanged)
    protocol_parser.py   (NEW -- standalone class, not BaseAgent)
    simulator.py         (unchanged)
    sdtm.py              (unchanged)
    adam.py               (unchanged)
    stats.py             (unchanged)
    medical_writer.py    (unchanged)
  config.py              (unchanged -- TrialConfig already has all fields)
  cli.py                 (MODIFIED -- add --protocol and --interactive flags)
  display/
    callbacks.py         (MODIFIED -- add InteractiveCallback protocol)
    pipeline_display.py  (unchanged)
    interactive_display.py (NEW -- InteractivePipelineDisplay subclass)
    error_display.py     (unchanged)
  llm/
    base.py              (unchanged)
    response_parser.py   (MODIFIED -- add extract_json function)
    gemini.py            (unchanged)
    openai_adapter.py    (unchanged)
  pipeline/
    orchestrator.py      (MODIFIED -- add _checkpoint method + calls,
                          add data_dictionary call in _run_track)
    data_dictionary.py   (NEW -- write_data_dictionary function)
    ...                  (all other pipeline modules unchanged)
  templates/prompts/
    protocol_parser.j2   (NEW)
    medical_writer.j2    (MODIFIED -- remove Section 8)
    ...                  (all other templates unchanged)
```

**Files created:** 4
**Files modified:** 5
**Files unchanged:** Everything else

---

## Anti-Patterns to Avoid

### Anti-Pattern 1: Making ProtocolParserAgent a BaseAgent Subclass

**What:** Inheriting from BaseAgent to "reuse" LLM calling code.
**Why bad:** BaseAgent's contract is "generate R code, execute in Docker." The protocol parser generates JSON, not R code. You would need to override `generate_code()` to skip R extraction, override `inject_seed()` to no-op, skip Docker execution entirely. The "reuse" is actually fighting the abstraction.
**Instead:** Standalone class that directly calls `BaseLLM.generate()`. The LLM call is 3 lines of code -- not worth an inheritance hierarchy.

### Anti-Pattern 2: Adding `input()` Calls Inside the Orchestrator

**What:** Putting `if self.interactive: input("Press Enter...")` directly in `orchestrator.run()`.
**Why bad:** Mixes UI concerns with pipeline logic. Makes the orchestrator untestable without mocking stdin. Breaks the clean callback separation that already exists.
**Instead:** Route through the callback protocol. The orchestrator calls `_checkpoint()`, the display handles user interaction.

### Anti-Pattern 3: Using the LLM to Generate the Data Dictionary

**What:** Having the ADaM agent or a new agent ask an LLM to write ADTTE variable descriptions.
**Why bad:** The data dictionary content is 100% deterministic. It is CDISC domain knowledge that does not change between runs. Using an LLM introduces non-determinism, latency, cost, and the possibility of hallucinated variable descriptions in a regulatory context. This is the worst possible place for an LLM.
**Instead:** Write it deterministically in Python from TrialConfig parameters.

### Anti-Pattern 4: Pausing Inside asyncio.gather()

**What:** Adding checkpoints between SDTM/ADaM/Stats within a track, which would require restructuring the parallel execution.
**Why bad:** Track A and Track B run in parallel via `asyncio.gather()`. Pausing one track while the other continues creates race conditions and confusing UX. Pausing BOTH tracks between every agent would serialize the entire pipeline, defeating the purpose of parallelism.
**Instead:** Pause at the boundaries between logical pipeline phases (after simulator, after both tracks, after comparison). These are natural synchronization points where the user can meaningfully inspect outputs.

### Anti-Pattern 5: Storing Protocol Parser Output in PipelineState

**What:** Recording the protocol parsing step in `pipeline_state.json` alongside SDTM, ADaM, etc.
**Why bad:** PipelineState tracks Docker execution results (R code, stdout, stderr, attempts). The protocol parser has none of these. Forcing it into PipelineState would require either nullable fields everywhere or a separate step model, adding complexity for marginal value.
**Instead:** Log the parsed TrialConfig to the run's log file. Optionally write `parsed_config.yaml` to the output directory for auditability.

---

## Suggested Build Order

Based on the dependency analysis above, the three features have no mutual dependencies. They can be built in any order. However, the following order is recommended for practical reasons:

### Phase 1: Data Dictionary Extraction

**Why first:** Smallest scope (1 new module, 1 template edit, 1 orchestrator line). Low risk. Independently testable. Delivers a clean CSR output improvement with minimal effort.

**Tasks:**
1. Create `data_dictionary.py` with `write_data_dictionary()`
2. Remove Section 8 from `medical_writer.j2`
3. Add call in `_run_track()` after ADaM validation
4. Write tests

**Estimated files:** 2 new, 2 modified

### Phase 2: Protocol Parser Agent

**Why second:** Medium scope. Requires a new agent class, prompt template, response parser addition, and CLI integration. Benefits from the stable codebase after Phase 1.

**Tasks:**
1. Add `extract_json()` to `response_parser.py`
2. Create `protocol_parser.j2` template
3. Create `ProtocolParserAgent` class
4. Add `--protocol` flag to CLI
5. Write tests (including edge cases: missing fields, ambiguous protocol text)

**Estimated files:** 2 new, 2 modified

### Phase 3: Interactive Execution Mode

**Why third:** Touches the most cross-cutting concerns (callback protocol, display layer, orchestrator, CLI). Benefits from having the other two features stable before adding pause points. Also, the interactive checkpoints become more useful when `--protocol` is available (can review extracted config before running).

**Tasks:**
1. Define `InteractiveCallback` protocol
2. Create `InteractivePipelineDisplay` class
3. Add `_checkpoint()` method to orchestrator
4. Add checkpoint calls at 3 pause points in `run()`
5. Add `--interactive` flag to CLI
6. Write tests (mock stdin, verify checkpoint sequencing)

**Estimated files:** 2 new, 3 modified

---

## Scalability Considerations

| Concern | Current (v1.2) | Future (v2.0+) |
|---------|----------------|-----------------|
| Protocol formats | .docx only | Could add .pdf, .txt, structured XML (via new parser classes) |
| Data dictionary scope | ADTTE only | Could expand to SDTM data dictionary, multiple ADaM datasets |
| Interactive granularity | Phase-level pauses | Could add per-agent pauses within tracks (requires refactoring _run_track) |
| Protocol parser validation | TrialConfig validation | Could add domain-specific validation (realistic SBP ranges, valid ratio formats) |

---

## Sources

- Direct codebase analysis of all files listed in project context (HIGH confidence)
- `python-docx` already in `pyproject.toml` dependencies (verified)
- `asyncio.get_event_loop().run_in_executor()` for blocking IO in async context (standard Python asyncio pattern, HIGH confidence)
- Rich `Live.stop()/start()` pattern for terminal handoff already demonstrated in `cli.py` and `PipelineDisplay` (HIGH confidence)
