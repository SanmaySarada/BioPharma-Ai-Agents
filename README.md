# omni-ai-agents

A multi-LLM clinical trial simulation and analysis pipeline. Generates synthetic
patient data, transforms it to CDISC regulatory standards, runs survival
analysis, independently validates results using a second LLM, and produces a
Clinical Study Report -- all from a single command.

The core idea: two different language models (Gemini and o3) independently
run the full analysis pipeline through separate code paths. Both tracks
produce SDTM, ADaM, and Stats outputs, which are compared stage-by-stage. When
tracks disagree, an adversarial resolution loop diagnoses which track erred,
provides targeted hints, and retries -- automatically. This catches errors that
any single model would miss -- a computational analog to the double programming
requirement in regulated biostatistics.

## Prerequisites

- **Python 3.13+**
- **Docker Desktop** -- the pipeline executes all R code inside isolated
  containers. Install from https://www.docker.com/products/docker-desktop/
  and make sure it is running before you start the pipeline.
- **API keys** for both LLM providers:
  - Gemini API key from https://aistudio.google.com/apikey
  - OpenAI API key from https://platform.openai.com/api-keys

## Setup

Clone the repository and create a virtual environment:

```
git clone <repo-url>
cd omni-ai-agents
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
```

Create a `.env` file in the project root with your API keys:

```
GEMINI_API_KEY=your-gemini-key-here
OPENAI_API_KEY=your-openai-key-here
```

The pipeline reads these via `python-dotenv` at startup. Never paste keys
directly into `config.yaml`.

## Running

```
omni-agents run --config config.yaml
```

Or use the module entry point:

```
python -m omni_agents.cli run --config config.yaml
```

### Interactive Mode

Add `--interactive` (or `-i`) to pause between major pipeline stages for
step-by-step review:

```
omni-agents run --config config.yaml --interactive
```

The pipeline pauses after the Simulator, after parallel track completion, and
after stage comparison/resolution. At each checkpoint you can inspect outputs
before continuing.

### Protocol Extraction

Extract trial parameters directly from a `.docx` protocol document:

```
omni-agents parse-protocol protocol.docx -o config.yaml
```

This reads the document, uses Gemini to extract trial parameters (n_subjects,
randomization ratio, endpoint, SBP distributions, dropout rate, etc.), displays
the extracted values alongside any defaults, and writes a ready-to-use
`config.yaml`. Fields not found in the protocol fall back to defaults and are
flagged.

The first run builds a Docker image (`omni-r-clinical:latest`) with R 4.5.2 and
all required statistical packages. This takes a few minutes. Subsequent runs
reuse the cached image.

The first run also calls both LLMs to generate R code. Generated scripts are
cached in `output/.script_cache/` keyed by trial configuration. Subsequent runs
with the same `config.yaml` skip LLM calls entirely and reuse cached scripts,
completing in about 10 seconds.

Output is written to `output/<timestamp>/`.

## Configuration

All trial parameters are in `config.yaml`:

```yaml
trial:
  n_subjects: 300          # patients in the simulated trial
  randomization_ratio: "2:1"  # treatment:placebo
  seed: 12345              # deterministic reproducibility
  visits: 26               # weekly visits including baseline
  endpoint: "SBP"          # systolic blood pressure
  treatment_sbp_mean: 120.0
  placebo_sbp_mean: 140.0
  baseline_sbp_mean: 150.0
  dropout_rate: 0.10       # 10% dropout before Week 26
  missing_rate: 0.03       # 3% random missing values per visit

docker:
  image: "omni-r-clinical:latest"
  memory_limit: "2g"
  timeout: 300             # kill container after 5 minutes
  network_disabled: true   # no internet inside containers

llm:
  gemini:
    api_key: $GEMINI_API_KEY
    model: "gemini-2.5-pro"
    temperature: 0.0
  openai:
    api_key: $OPENAI_API_KEY
    model: "o3"
    temperature: 0.0

resolution:
  enabled: true              # attempt automated resolution on disagreement
  max_iterations: 2          # max retry cycles before halting or picking best
```

Changing any trial parameter invalidates the script cache, so the next run will
call the LLMs again to regenerate R code for the new configuration.

Set `resolution.enabled: false` to halt immediately on any stage disagreement
instead of attempting automated resolution.

## Pipeline Architecture

The pipeline has 9 agent steps organized into 5 stages. Each agent is a
stateless worker: it receives context, calls an LLM to generate R code, and the
orchestrator executes that code in a sandboxed Docker container.

```
Stage 1           Stage 2                        Stage 3            Stage 4          Stage 5
Simulation        Analysis                       Comparison         Resolution       Reporting
                  (parallel)                     (sequential)       (if needed)      (sequential)

               +--[SDTM]--[ADaM]--[Stats]--+
               |       Track A (Gemini)     |
[Simulator] ---+                            +---[Stage          ---[Resolution]----[Medical Writer]
               |       Track B (o3)         |    Comparator]       Loop
               +--[SDTM]--[ADaM]--[Stats]--+
```

### Stage 1: Data Generation

**Simulator Agent** (Gemini) generates a synthetic clinical trial dataset.

- Input: Trial parameters from config (n_subjects, visits, randomization ratio,
  SBP distributions, dropout/missing rates)
- LLM generates R code that creates the dataset using `set.seed()` for
  reproducibility
- Output: `raw/SBPdata.csv` -- 7,800 rows (300 subjects x 26 visits) with
  columns USUBJID, ARM, AGE, SEX, RACE, VISIT, SBP
- The orchestrator validates output structure (column names, row count, arm
  distribution) before proceeding

### Stage 2: Parallel Analysis

Track A and Track B execute simultaneously via `asyncio.gather()`. Both tracks
run the identical three-agent pipeline (SDTM, ADaM, Stats) but with different
LLMs generating different R code. Docker volume mounts enforce physical
isolation -- neither track can access the other's files.

Each track runs three agents sequentially, each reading the previous agent's
output:

**SDTM Agent** maps raw data to CDISC Study Data Tabulation Model format.

- Input: `raw/SBPdata.csv`
- Output: `{track}/sdtm/DM.csv` (Demographics, 300 rows, 12 CDISC columns) and
  `{track}/sdtm/VS.csv` (Vital Signs, 7,800 rows, 12 CDISC columns)
- Schema validation checks column names, controlled terminology (VSTESTCD, RACE,
  SEX values), row counts, and referential integrity (every VS subject exists in
  DM)
- Per-dataset data dictionaries are generated for DM and VS

**ADaM Agent** derives the Analysis Data Model datasets.

- Input: SDTM DM.csv and VS.csv
- Output:
  - `{track}/adam/ADSL.csv` -- subject-level analysis dataset (one row per
    subject with demographics, treatment variables, population flags, and
    disposition)
  - `{track}/adam/ADSL_summary.json` -- machine-readable ADSL validation sidecar
  - `{track}/adam/ADTTE.rds` -- time-to-event dataset for R consumption by Stats
  - `{track}/adam/ADTTE.xlsx` -- time-to-event dataset for human review
  - `{track}/adam/ADTTE_summary.json` -- machine-readable ADTTE validation sidecar
- ADSL is constructed first and saved before ADTTE. ADTTE merges subject-level
  variables from the in-memory ADSL dataframe (not DM directly)
- Event definition: first post-baseline visit where SBP drops below 120 mmHg.
  Patients who never reach this threshold or who drop out are censored.
- Schema validation checks:
  - ADSL row count matches n_subjects, required columns present
  - EFFFL (Efficacy Population Flag) distribution: flags if all subjects are
    marked "Y", which indicates a derivation bug since dropouts should have no
    post-baseline data
  - ADTTE row count, PARAMCD, event + censored totals
  - n_censored > 0 (catches `min(empty, na.rm=TRUE)` returning `Inf` being
    misclassified as an event)
  - Event rate below 95% (flags implausible upstream derivations)
- Per-dataset data dictionaries are generated for ADSL and ADTTE
- Output completeness gate verifies all data dictionaries, ADSL.csv, and
  ADTTE.xlsx are present before proceeding

**Stats Agent** runs the survival analysis.

- Input: ADTTE.rds and SDTM DM.csv
- Output:
  - `table1_demographics.csv` -- demographics by treatment arm (age, sex, race,
    baseline SBP) with p-values for balance
  - `table2_km_results.csv` -- Kaplan-Meier median survival times per arm,
    log-rank chi-squared and p-value
  - `table3_cox_results.csv` -- Cox proportional hazards model: hazard ratio
    with 95% CI for treatment effect, adjusted for age and sex
  - `km_plot.png` -- Kaplan-Meier survival curves with number-at-risk table
  - `results.json` -- all statistics at full numerical precision (display values
    rounded to 4 decimal places)
- Schema validation checks all expected files exist and results.json has
  required fields

Track A uses Gemini; Track B uses o3. The same agent code runs for both --
the orchestrator's generic `_run_track` method parameterizes by track ID and
LLM, ensuring identical pipeline structure with independent code generation.

The OpenAI adapter automatically uses the `developer` message role (instead of
`system`) for o3-series reasoning models, ensuring prompt instructions receive
full priority.

### Stage 3: Stage Comparison

**StageComparator** is a deterministic comparison module (no LLM call). It
compares Track A and Track B outputs at every pipeline stage:

**SDTM comparison** checks:
- Row counts for DM and VS datasets
- Column sets match between tracks
- Subject ID overlap
- ARM, SEX, and RACE distribution alignment

**ADaM comparison** checks:
- Row count, event count, censored count
- PARAMCD values match
- Column sets match

**Stats comparison** uses tolerance-based matching:

| Metric | Tolerance | Type |
|--------|-----------|------|
| n_subjects | must match exactly | exact |
| n_events | must match exactly | exact |
| n_censored | must match exactly | exact |
| log-rank p-value | +/- 0.001 | absolute |
| Cox hazard ratio | +/- 0.1% | relative |
| KM median (treatment) | +/- 0.5 | absolute |
| KM median (placebo) | +/- 0.5 | absolute |

Output: `consensus/stage_comparisons.json` with per-stage results.

### Stage 4: Resolution (if needed)

When stage comparison finds a disagreement, the **ResolutionLoop** activates:

1. **Diagnose** -- deterministic heuristic identifies which track likely erred
   (e.g., the track with fewer rows is probably wrong)
2. **Generate hint** -- creates a structured hint with the specific discrepancies
   and stage-appropriate suggested checks
3. **Retry** -- the failing track re-runs from the disagreeing stage with the
   hint injected via the error-feedback mechanism. Downstream stages cascade
   (e.g., fixing SDTM triggers ADaM and Stats re-runs)
4. **Re-compare** -- StageComparator runs again on the new outputs

This repeats up to `max_iterations` (default: 2). If resolution succeeds, the
pipeline proceeds. If it fails, the system either selects the best track or
halts.

Verdict logic:

- **PASS** -- all stages agree within tolerance. Pipeline proceeds.
- **WARNING** -- resolution selected a winning track after exhausting iterations
  but tracks still disagree. Pipeline proceeds with the winner's outputs and a
  caution flag embedded in the CSR.
- **HALT** -- disagreement persists and no winner could be determined. Pipeline
  stops and writes a diagnostic report.

Output: `consensus/verdict.json`, `consensus/stage_comparisons.json`,
`consensus/resolution_log.json` (if resolution triggered)

### Stage 5: Reporting

**Medical Writer Agent** (Gemini) generates the Clinical Study Report.

- Input: winning track's `stats/results.json`, all three CSV tables,
  `km_plot.png`, and `consensus/verdict.json`
- LLM generates R code using the `officer`, `flextable`, `jsonlite`, and `readr`
  packages to produce a Word document
- Output: `csr/clinical_study_report.docx` containing:
  - Narrative summary of study results with statistical interpretations
  - Tables 1-3 formatted as flextables
  - KM plot embedded as an image
  - Internal cross-references linking cited statistics to their source tables
  - If consensus verdict was WARNING, the report includes the caution flag and
    investigation hints

## Output Structure

Each run produces a timestamped directory:

```
output/20260211_074448/
  raw/
    SBPdata.csv              # synthetic trial data (7,800 rows)
    script.R                 # R code that generated it
  track_a/
    sdtm/
      DM.csv                 # CDISC Demographics (300 rows)
      VS.csv                 # CDISC Vital Signs (7,800 rows)
      DM_data_dictionary.csv # DM variable definitions
      VS_data_dictionary.csv # VS variable definitions
      script.R
    adam/
      ADSL.csv               # subject-level analysis dataset (300 rows)
      ADSL_summary.json      # ADSL validation sidecar
      ADSL_data_dictionary.csv  # ADSL variable definitions
      ADTTE.rds              # time-to-event dataset (R format)
      ADTTE.xlsx             # time-to-event dataset (Excel)
      ADTTE_summary.json     # ADTTE validation sidecar
      ADTTE_data_dictionary.csv # ADTTE variable definitions
      script.R
    stats/
      table1_demographics.csv
      table2_km_results.csv
      table3_cox_results.csv
      km_plot.png            # Kaplan-Meier survival curves
      results.json           # full-precision statistics
      script.R
  track_b/
    sdtm/
      DM.csv                 # independent SDTM from o3
      VS.csv
      DM_data_dictionary.csv
      VS_data_dictionary.csv
      script.R
    adam/
      ADSL.csv               # independent ADSL from o3
      ADSL_summary.json
      ADSL_data_dictionary.csv
      ADTTE.rds              # independent ADaM from o3
      ADTTE.xlsx
      ADTTE_summary.json
      ADTTE_data_dictionary.csv
      script.R
    stats/
      table1_demographics.csv
      table2_km_results.csv
      table3_cox_results.csv
      km_plot.png
      results.json           # independent statistics from o3
      script.R
  consensus/
    stage_comparisons.json   # per-stage comparison results
    resolution_log.json      # resolution attempts (if triggered)
    verdict.json             # PASS / WARNING / HALT
  csr/
    clinical_study_report.docx  # final regulatory document
    script.R
  logs/
    <run_id>/
      pipeline.jsonl         # structured log with token counts
  pipeline_state.json        # audit trail of every agent step
```

Every `script.R` file is the exact R code that was generated by the LLM and
executed in Docker, preserved for reproducibility and audit.

## Error Handling

Each agent's R code goes through a generate-validate-execute-retry loop:

1. **Generate** -- LLM produces R code from a Jinja2 prompt template
2. **Pre-execution validation** -- checks that the code references expected
   input files, produces expected outputs, loads only allowed R packages, and
   doesn't use disallowed functions
3. **Docker execution** -- code runs in an isolated container with memory
   limits, CPU limits, network disabled, and a 5-minute timeout
4. **Stderr filtering** -- R packages (tidyverse, survminer) print verbose
   loading messages to stderr that obscure real errors. A regex-based filter
   strips package-attach noise, masking warnings, and tidyverse banners,
   keeping only the actual error for classification and LLM feedback.
5. **Error classification** -- the filtered stderr is classified:
   - Code bug or data path error: retried (error fed back to LLM)
   - Timeout: retried (LLM may generate simpler code)
   - Missing R package: not retried (Docker image needs fixing)
   - Statistical convergence failure: not retried (data issue)
6. **Retry** -- up to 3 attempts. The LLM receives the filtered error output
   as context, which resolves most code errors on the first retry.

Prompt templates include defensive coding patterns for known R pitfalls --
for example, the ADaM prompt warns that `min(integer(0), na.rm = TRUE)` returns
`Inf` (not `NA`), and the Stats prompt includes data-cleaning preamble that
filters `Inf`/`NA` rows before survival analysis. The Stats prompt also
documents the exact column names returned by `summary(survfit)$table` (e.g.,
`"records"` not `"n"`) to prevent LLMs from guessing wrong accessor names.

If all retries fail, the CLI displays a structured error panel identifying the
agent, error class, message, and suggested fix.

R scripts are cached on first successful generation. Cache keys are derived
from the trial configuration hash, agent name, and track ID, so any config
change produces a cache miss. Track-aware keys prevent Track A and Track B from
colliding in the cache.

## Docker Isolation

All R code executes inside Docker containers, never on the host. Each agent gets
its own container with:

- **Network disabled** -- containers cannot make outbound requests
- **Memory limit** -- 2 GB default, prevents runaway allocations
- **CPU limit** -- 1 core default
- **Timeout** -- 300 seconds, container is killed if exceeded
- **Read-only input volumes** -- agents can read upstream outputs but cannot
  modify them
- **Writable workspace** -- one directory per agent for output

Each track's containers mount only the raw data directory plus that track's own
upstream outputs. Neither track can access the other's files.

## Project Structure

```
src/omni_agents/
  cli.py                     # Typer CLI entry point (run + parse-protocol)
  config.py                  # Pydantic settings (YAML + env var resolution)
  agents/
    base.py                  # BaseAgent ABC: prompt loading, code generation
    simulator.py             # Synthetic data generation
    sdtm.py                  # CDISC SDTM mapping
    adam.py                  # ADaM ADSL + ADTTE derivation
    stats.py                 # Survival analysis (KM, Cox, demographics)
    medical_writer.py        # CSR document generation
    protocol_parser.py       # Protocol document extraction (parse-protocol)
    docx_reader.py           # .docx text extraction utility
    double_programmer.py     # (deprecated) Legacy single-agent validation
  display/
    callbacks.py             # ProgressCallback protocol (9 lifecycle hooks)
    pipeline_display.py      # Rich Live terminal UI (9 pipeline steps)
    interactive_display.py   # Interactive mode with checkpoint pauses
    error_display.py         # Structured error panels
  docker/
    engine.py                # Docker SDK wrapper (image build, container lifecycle)
    r_executor.py            # R script execution with volume mounts
  llm/
    base.py                  # BaseLLM abstract class and LLMResponse model
    gemini.py                # Google Gemini adapter
    openai_adapter.py        # OpenAI o3 adapter (developer role for reasoning models)
    response_parser.py       # R code extraction from LLM markdown responses
  models/
    consensus.py             # ConsensusVerdict, MetricComparison models
    execution.py             # DockerResult, AgentAttempt, ErrorClassification
    pipeline.py              # PipelineState, StepState for audit trail
    resolution.py            # TrackResult, StageComparison, ResolutionHint, ResolutionResult
    schemas.py               # CDISC column definitions and validation constants
  pipeline/
    orchestrator.py          # Main pipeline DAG: symmetric fork, compare, resolve, report
    consensus.py             # ConsensusJudge comparison logic
    resolution.py            # ResolutionLoop: diagnose, hint, cascade re-run
    retry.py                 # Error-feedback retry loop with classification
    schema_validator.py      # SDTM/ADaM/Stats output validation + EFFFL + completeness
    script_cache.py          # SHA-256 keyed R script cache (track-aware)
    stage_comparator.py      # Per-stage comparison: SDTM, ADaM, Stats
    stderr_filter.py         # R stderr noise removal (package loading, masking warnings)
    pre_execution.py         # Static R code analysis before Docker execution
    data_dictionary.py       # Per-dataset data dictionary generation (DM, VS, ADSL, ADTTE)
    logging.py               # Loguru setup with structured JSONL and token logging
  templates/
    prompts/
      simulator.j2           # Jinja2 prompt for data generation
      sdtm.j2                # Jinja2 prompt for CDISC SDTM mapping
      adam.j2                # Jinja2 prompt for ADSL + ADTTE derivation
      stats.j2               # Jinja2 prompt for survival analysis
      medical_writer.j2      # Jinja2 prompt for CSR generation
      protocol_parser.j2     # Jinja2 prompt for protocol extraction
      double_programmer.j2   # (deprecated) Legacy validation prompt
docker/
  r-clinical/
    Dockerfile               # R 4.5.2 + 12 statistical packages
    healthcheck.R            # Package load verification
```

## Reproducibility

Given the same `config.yaml`:

1. `set.seed()` is injected into every R script by the orchestrator, ensuring
   identical random number sequences
2. R scripts are cached after first generation -- subsequent runs execute the
   exact same code
3. Docker image pins R version (4.5.2) and package versions via Posit Package
   Manager snapshots
4. `pipeline_state.json` records every step, its generated code, stdout/stderr,
   timing, and attempt count
5. All generated R scripts are saved alongside their outputs for audit

Two runs with the same config and seed will produce identical datasets and
identical statistical results.

## Development

```
pip install -e ".[dev]"
ruff check src/
mypy src/omni_agents/
pytest
```
