# omni-ai-agents

A multi-LLM clinical trial simulation and analysis pipeline. Generates synthetic
patient data, transforms it to CDISC regulatory standards, runs survival
analysis, independently validates results using a second LLM, and produces a
Clinical Study Report -- all from a single command.

The core idea: two different language models (Gemini and GPT-4) independently
analyze the same trial data through separate code paths. A deterministic
Consensus Judge compares their statistical results. If the models disagree
beyond metric-specific tolerances, the pipeline halts. This catches errors that
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
python -m omni_agents.cli --config config.yaml
```

Or use the installed entry point:

```
omni-agents --config config.yaml
```

The first run builds a Docker image (`omni-r-clinical:latest`) with R 4.5 and
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
    model: "gpt-4o"
    temperature: 0.0
```

Changing any trial parameter invalidates the script cache, so the next run will
call the LLMs again to regenerate R code for the new configuration.

## Pipeline Architecture

The pipeline has 7 agent steps organized into 4 stages. Each agent is a
stateless worker: it receives context, calls an LLM to generate R code, and the
orchestrator executes that code in a sandboxed Docker container.

```
Stage 1           Stage 2                        Stage 3           Stage 4
Simulation        Analysis                       Validation        Reporting
                  (parallel)                     (sequential)      (sequential)

               +--[SDTM]--[ADaM]--[Stats]--+
               |       Track A (Gemini)     |
[Simulator] ---+                            +---[Consensus]------[Medical Writer]
               |       Track B (GPT-4)      |     Judge
               +--[Double Programmer]-------+
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

Track A and Track B execute simultaneously via `asyncio.gather()`. Docker volume
mounts enforce physical isolation -- Track B cannot access any Track A files.

#### Track A (Gemini) -- Full Regulatory Pipeline

Three agents run sequentially, each reading the previous agent's output:

**SDTM Agent** maps raw data to CDISC Study Data Tabulation Model format.

- Input: `raw/SBPdata.csv`
- Output: `track_a/sdtm/DM.csv` (Demographics, 300 rows, 12 CDISC columns) and
  `track_a/sdtm/VS.csv` (Vital Signs, 7,800 rows, 12 CDISC columns)
- Schema validation checks column names, controlled terminology (VSTESTCD, RACE,
  SEX values), row counts, and referential integrity (every VS subject exists in
  DM)

**ADaM Agent** derives the Analysis Data Model for time-to-event analysis.

- Input: SDTM DM.csv and VS.csv
- Output: `track_a/adam/ADTTE.rds` (time-to-event dataset) and
  `track_a/adam/ADTTE_summary.json` (machine-readable validation sidecar)
- Event definition: first post-baseline visit where SBP drops below 120 mmHg.
  Patients who never reach this threshold or who drop out are censored.
- Schema validation checks row count matches n_subjects, PARAMCD is correct,
  event + censored counts sum to total subjects

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

#### Track B (GPT-4) -- Independent Validation

**Double Programmer Agent** replicates the key statistical results from scratch.

- Input: only `raw/SBPdata.csv` (no access to SDTM, ADaM, or Track A stats)
- Output: `track_b/validation.json` with `validator_p_value`, `validator_hr`,
  and metadata (n_subjects, n_events, n_censored)
- GPT-4 generates its own R code to independently calculate the log-rank
  p-value and Cox hazard ratio directly from raw data
- Docker volume mounts ensure Track B physically cannot read Track A outputs

### Stage 3: Consensus

**Consensus Judge** is a deterministic comparison module (no LLM call). It
compares Track A and Track B on five metrics with specific tolerances:

| Metric | Tolerance | Type |
|--------|-----------|------|
| n_subjects | must match exactly | exact |
| n_events | must match exactly | exact |
| n_censored | must match exactly | exact |
| log-rank p-value | +/- 0.001 | absolute |
| Cox hazard ratio | +/- 0.1% | relative |

Verdict logic:

- **PASS** -- all metrics within tolerance. Pipeline proceeds.
- **WARNING** -- metrics are within tolerance but a p-value straddles a
  significance boundary (e.g., 0.045 vs 0.055). Pipeline proceeds with a
  caution flag embedded in the CSR.
- **HALT** -- any metric outside tolerance. Pipeline stops and writes a
  diagnostic report with per-metric values, differences, and investigation
  hints. This means the two models produced meaningfully different statistical
  results from the same data, indicating a code generation error.

Output: `consensus/verdict.json`

### Stage 4: Reporting

**Medical Writer Agent** (Gemini) generates the Clinical Study Report.

- Input: `track_a/stats/results.json`, all three CSV tables, `km_plot.png`, and
  `consensus/verdict.json`
- LLM generates R code using the `officer` and `flextable` packages to produce
  a Word document
- Output: `csr/clinical_study_report.docx` containing:
  - Narrative summary of study results with statistical interpretations
  - Tables 1-3 formatted as flextables
  - KM plot embedded as an image
  - Internal cross-references linking cited statistics to their source tables
  - Data dictionary explaining ADTTE variable derivations
  - If consensus verdict was WARNING, the report includes the caution flag and
    boundary warnings

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
      script.R
    adam/
      ADTTE.rds              # time-to-event dataset
      ADTTE_summary.json     # validation sidecar
      script.R
    stats/
      table1_demographics.csv
      table2_km_results.csv
      table3_cox_results.csv
      km_plot.png            # Kaplan-Meier survival curves
      results.json           # full-precision statistics
      script.R
  track_b/
    validation.json          # GPT-4 independent results
    script.R
  consensus/
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
4. **Error classification** -- if execution fails, stderr is classified:
   - Code bug or data path error: retried (error fed back to LLM)
   - Timeout: retried (LLM may generate simpler code)
   - Missing R package: not retried (Docker image needs fixing)
   - Statistical convergence failure: not retried (data issue)
5. **Retry** -- up to 3 attempts. The LLM receives the previous error output
   as context, which resolves most code errors on the first retry.

If all retries fail, the CLI displays a structured error panel identifying the
agent, error class, message, and suggested fix.

R scripts are cached on first successful generation. Cache keys are derived
from the trial configuration hash and agent name, so any config change produces
a cache miss.

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

Track B's container mounts only the raw data directory. It physically cannot
access Track A's SDTM, ADaM, or statistics directories.

## Project Structure

```
src/omni_agents/
  cli.py                     # Typer CLI entry point
  config.py                  # Pydantic settings (YAML + env var resolution)
  agents/
    base.py                  # BaseAgent ABC: prompt loading, code generation
    simulator.py             # Synthetic data generation
    sdtm.py                  # CDISC SDTM mapping
    adam.py                   # ADaM time-to-event derivation
    stats.py                 # Survival analysis (KM, Cox, demographics)
    double_programmer.py     # Independent GPT-4 validation
    medical_writer.py        # CSR document generation
  display/
    callbacks.py             # ProgressCallback protocol (7 lifecycle hooks)
    pipeline_display.py      # Rich Live terminal UI
    error_display.py         # Structured error panels
  docker/
    engine.py                # Docker SDK wrapper (image build, container lifecycle)
    r_executor.py            # R script execution with volume mounts
  llm/
    base.py                  # BaseLLM abstract class and LLMResponse model
    gemini.py                # Google Gemini adapter
    openai_adapter.py        # OpenAI GPT-4 adapter
    response_parser.py       # R code extraction from LLM markdown responses
  models/
    consensus.py             # ConsensusVerdict, MetricComparison models
    execution.py             # DockerResult, AgentAttempt, ErrorClassification
    pipeline.py              # PipelineState, StepState for audit trail
    schemas.py               # CDISC column definitions and validation constants
  pipeline/
    orchestrator.py          # Main pipeline DAG: fork, gather, consensus gate
    consensus.py             # ConsensusJudge comparison logic
    retry.py                 # Error-feedback retry loop with classification
    schema_validator.py      # SDTM/ADaM/Stats output validation
    script_cache.py          # SHA-256 keyed R script cache
    pre_execution.py         # Static R code analysis before Docker execution
    logging.py               # Loguru setup with structured JSONL and token logging
  templates/
    prompts/
      simulator.j2           # Jinja2 prompt for data generation
      sdtm.j2                # Jinja2 prompt for CDISC SDTM mapping
      adam.j2                # Jinja2 prompt for ADaM derivation
      stats.j2               # Jinja2 prompt for survival analysis
      double_programmer.j2   # Jinja2 prompt for independent validation
      medical_writer.j2      # Jinja2 prompt for CSR generation
docker/
  r-clinical/
    Dockerfile               # R 4.5 + 11 statistical packages
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

## License

MIT
