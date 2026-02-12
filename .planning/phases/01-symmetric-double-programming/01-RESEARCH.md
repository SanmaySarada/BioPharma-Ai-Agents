# Phase 1: Symmetric Double Programming Architecture - Research

**Researched:** 2026-02-11
**Domain:** Multi-LLM clinical trial validation pipeline / N-version programming / adversarial resolution
**Confidence:** HIGH (codebase analysis) / MEDIUM (architecture patterns) / MEDIUM (resolution protocol)

## Summary

This research addresses the redesign of a dual-track clinical trial analysis pipeline from an asymmetric architecture (Track A: full 3-stage pipeline, Track B: simplified single-stage validation) to a symmetric architecture where both tracks independently execute the full SDTM -> ADaM -> Stats pipeline, with stage-by-stage comparison and an adversarial resolution loop for disagreements.

The existing codebase is well-structured for this change. The agent classes (`SDTMAgent`, `ADaMAgent`, `StatsAgent`) are stateless workers that accept an LLM adapter via constructor injection. The `BaseAgent` class uses a `BaseLLM` interface with `GeminiAdapter` and `OpenAIAdapter` implementations. This means Track B can reuse the exact same agent classes by injecting `OpenAIAdapter` instead of `GeminiAdapter` -- no new agent classes needed. The `DoubleProgrammerAgent` and its prompt template become deprecated.

The key architectural decisions center on three areas: (1) how to structure stage-by-stage comparison without breaking parallel execution, (2) how to design the adversarial resolution protocol when tracks disagree, and (3) how the existing code-level retry loop interacts with the new semantic-level resolution loop.

**Primary recommendation:** Use a "fully parallel, then stage-by-stage comparison" architecture. Run both tracks completely in parallel (preserving current latency), then compare outputs at each stage post-hoc. When disagreement is found at a stage, restart only the failing track from that stage with targeted hints. Use deterministic validation as the primary arbiter (not a third LLM). Limit resolution to 2 iterations maximum.

## Standard Stack

### Core (Already in Codebase)
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| asyncio | stdlib | Parallel track execution | Already used for `asyncio.gather()` of Track A/B |
| pydantic | v2 | Models for comparison results, resolution state | Already used for all data models |
| loguru | current | Structured logging | Already in use |
| jinja2 | current | Prompt templates | Already in use for agent prompts |

### New Components Needed
| Component | Type | Purpose | Notes |
|-----------|------|---------|-------|
| `StageComparator` | New class | Compare outputs at each pipeline stage | Replaces current `ConsensusJudge` for stage-level |
| `ResolutionLoop` | New class | Orchestrate adversarial resolution when stages disagree | New concept, not in current codebase |
| `TrackRunner` | New class or method | Encapsulate the 3-stage pipeline for either track | Refactor of `_run_track_a` to be track-agnostic |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| Deterministic arbiter | Third LLM as judge | 3rd LLM adds cost, latency, and a new failure mode. Deterministic rules are auditable and reproducible. Use LLM arbiter only as escalation. |
| `asyncio.Barrier` for stage sync | `asyncio.gather()` per stage | Barrier adds complexity. Since we recommend post-hoc comparison, barriers are unnecessary. |
| New `TrackBSDTMAgent`, etc. | Reuse existing agents with different LLM | Separate agents would duplicate code. Existing agents are parameterized by LLM adapter already. |

## Architecture Patterns

### Recommended Project Structure Changes
```
src/omni_agents/
  pipeline/
    orchestrator.py        # MODIFIED: new symmetric track runner, resolution loop
    consensus.py           # MODIFIED: stage-level comparison (not just final stats)
    retry.py               # UNCHANGED: code-level retry stays as-is
    resolution.py          # NEW: adversarial resolution loop for semantic disagreements
    stage_comparator.py    # NEW: per-stage output comparison logic
  agents/
    sdtm.py                # UNCHANGED
    adam.py                 # UNCHANGED
    stats.py               # UNCHANGED
    double_programmer.py   # DEPRECATED (keep for backward compat, mark deprecated)
  models/
    consensus.py           # MODIFIED: new StageComparison, ResolutionResult models
    resolution.py          # NEW: resolution state models (hints, iteration tracking)
  templates/prompts/
    sdtm.j2                # UNCHANGED (both tracks use same prompts)
    adam.j2                # UNCHANGED
    stats.j2               # UNCHANGED
    double_programmer.j2   # DEPRECATED
```

Output directory structure change:
```
{run_id}/
  raw/SBPdata.csv
  track_a/
    sdtm/DM.csv, VS.csv, script.R
    adam/ADTTE.rds, ADTTE_summary.json, script.R
    stats/results.json, km_plot.png, tables, script.R
  track_b/                    # CHANGED: now mirrors track_a structure
    sdtm/DM.csv, VS.csv, script.R
    adam/ADTTE.rds, ADTTE_summary.json, script.R
    stats/results.json, km_plot.png, tables, script.R
  consensus/
    stage_comparisons.json    # NEW: per-stage comparison results
    verdict.json              # MODIFIED: includes stage-level detail
    resolution_log.json       # NEW: if resolution was triggered
  csr/...
```

### Pattern 1: Symmetric Track Runner (Refactor _run_track_a into Generic)

**What:** Extract the current `_run_track_a` method into a generic `_run_track` that accepts a track identifier and LLM adapter.

**When to use:** Always -- this is the core architectural change.

**Why it works:** The existing `SDTMAgent`, `ADaMAgent`, and `StatsAgent` classes are already parameterized by `llm: BaseLLM`. They have no Gemini-specific code. The prompt templates are model-agnostic (they describe R code generation, not LLM-specific formatting). The only change needed is passing `OpenAIAdapter` instead of `GeminiAdapter` for Track B.

**Example:**
```python
async def _run_track(
    self,
    track_id: str,  # "track_a" or "track_b"
    llm: BaseLLM,   # GeminiAdapter or OpenAIAdapter
    raw_dir: Path,
    output_dir: Path,
    prompt_dir: Path,
    state: PipelineState,
    state_path: Path,
) -> TrackResult:
    """Run full SDTM -> ADaM -> Stats pipeline for one track."""
    track_dir = output_dir / track_id

    # SDTM
    sdtm_dir = track_dir / "sdtm"
    sdtm_dir.mkdir(parents=True, exist_ok=True)
    sdtm_agent = SDTMAgent(llm=llm, prompt_dir=prompt_dir, trial_config=self.settings.trial)
    # ... same as current _run_track_a SDTM section but with track_id

    # ADaM
    adam_dir = track_dir / "adam"
    # ... same pattern

    # Stats
    stats_dir = track_dir / "stats"
    # ... same pattern

    return TrackResult(
        track_id=track_id,
        sdtm_dir=sdtm_dir,
        adam_dir=adam_dir,
        stats_dir=stats_dir,
        results_path=stats_dir / "results.json",
    )
```

**Key detail:** The existing `_run_agent` method, `execute_with_retry`, script caching, schema validation, and Docker isolation all work unchanged. Each track gets its own `work_dir` and `input_volumes`, so Docker containers are already isolated between tracks.

### Pattern 2: Post-Hoc Stage-by-Stage Comparison

**What:** Run both tracks fully in parallel, then compare at each stage after both complete.

**When to use:** Always -- this is the recommended comparison strategy (see Analysis below).

**Analysis of comparison timing strategies:**

| Strategy | Latency | Complexity | Benefit |
|----------|---------|------------|---------|
| **A: Full parallel, compare at end** | Best (current) | Lowest | Simple, preserves current architecture |
| **B: Stage-gated (barrier after each stage)** | Worst (~3x sequential) | Highest | Catches errors early, saves downstream compute |
| **C: Full parallel, then stage-by-stage comparison** | Same as A | Medium | Best of both: parallel speed + granular diagnosis |

**Strategy C is recommended** because:
1. It preserves the current `asyncio.gather()` parallelism (no latency regression)
2. It provides stage-level diagnosis when disagreement occurs (better than strategy A)
3. It avoids the `asyncio.Barrier` complexity and latency hit of strategy B
4. When tracks agree, there is zero overhead vs. current approach
5. When tracks disagree, the stage-level comparison pinpoints WHERE divergence started, enabling targeted resolution

**Why NOT stage-gated (Strategy B):** In the current pipeline, each stage takes 30-90 seconds (LLM generation + Docker execution). With barriers, you serialize: Track A SDTM finishes, waits for Track B SDTM, compare, then both proceed to ADaM. Total time becomes sum of max(stage_time) across both tracks at each stage, plus comparison time. This roughly doubles latency in the best case and prevents any benefit from one track being faster.

**Example:**
```python
# In orchestrator.run():

# 1. Run both tracks fully in parallel (same as current)
track_a_result, track_b_result = await asyncio.gather(
    self._run_track("track_a", gemini, ...),
    self._run_track("track_b", openai, ...),
)

# 2. Compare stage-by-stage AFTER both complete
comparisons = StageComparator.compare_all_stages(track_a_result, track_b_result)

# 3. If all stages agree -> proceed to medical writer
# 4. If any stage disagrees -> enter resolution loop
if comparisons.has_disagreement:
    resolved = await self._resolve_disagreement(
        comparisons, track_a_result, track_b_result, ...
    )
```

### Pattern 3: Two-Layer Error Handling (Code Retry vs. Semantic Resolution)

**What:** The existing `execute_with_retry` loop handles code-level errors (syntax, runtime). The new resolution loop handles semantic-level disagreements (both tracks produce valid output but different results).

**When to use:** Critical to keep these separate. They operate at different levels.

```
Layer 1: Code-Level Retry (EXISTING - unchanged)
  Trigger: R code crashes, syntax error, timeout, missing file
  Handler: execute_with_retry() in retry.py
  Max attempts: 3
  Feedback: R stderr -> LLM for code fix
  Scope: Within a single track, single stage

Layer 2: Semantic Resolution (NEW)
  Trigger: Both tracks produce valid output but disagree on values
  Handler: ResolutionLoop in resolution.py
  Max iterations: 2
  Feedback: Structured comparison diff + hints -> LLM for re-derivation
  Scope: Cross-track, at the disagreeing stage
```

**Interaction:** Layer 1 runs first (inside `_run_track`). If a track's code crashes, it retries with error feedback up to 3 times. Only after both tracks produce schema-valid output does Layer 2 activate. If Layer 2 triggers a re-run of a stage, that re-run still uses Layer 1 for code-level retries.

### Pattern 4: Adversarial Resolution Protocol

**What:** When stage comparison reveals disagreement, a structured resolution process determines which track went wrong and re-runs only that track with hints.

**Design (recommended -- based on N-version programming and clinical trial double programming practices):**

```
Resolution Protocol:
1. DETECT: StageComparator finds disagreement at stage S
2. DIAGNOSE: Deterministic validation rules check which track's output
   is more likely correct (schema compliance, referential integrity,
   value range plausibility, CDISC compliance)
3. HINT: Generate a structured hint for the failing track containing:
   - The specific discrepancy found (e.g., "Your DM.csv has 298 subjects,
     other track has 300. Check your deduplication logic.")
   - The relevant validation rule that was violated (if applicable)
   - NOT the other track's full output (to maintain independence)
4. RETRY: Re-run ONLY the failing track from stage S with the hint
   injected into the agent's context
5. RE-COMPARE: Compare the new output with the other track's output
6. TERMINATE: After max 2 iterations, if still disagreeing:
   - If deterministic validation strongly favors one track -> use it
   - Otherwise -> HALT with diagnostic report
```

### Anti-Patterns to Avoid

- **Full output sharing between tracks:** Showing Track A's complete SDTM output to Track B defeats independence. The hint should describe the DISCREPANCY, not provide the answer.
- **Third LLM as primary arbiter:** Adding a third LLM model increases cost, latency, and introduces a new failure mode. Deterministic validation rules should be the primary arbiter. LLM-based judgment should be an optional future enhancement, not the initial design.
- **Unbounded resolution loops:** Multi-agent debate research (Du et al., ICML 2024) shows diminishing returns after 2-3 rounds. For code generation specifically, if two different LLMs independently produce different R code that both run successfully but yield different numbers, further debate rounds rarely converge. The issue is usually a specification ambiguity (e.g., how to handle NA values) that needs a deterministic rule, not more LLM calls.
- **Stage-gated barriers:** Using `asyncio.Barrier` to synchronize tracks at each stage adds latency and complexity with minimal benefit for this use case. Post-hoc comparison achieves the same diagnostic power.
- **Restarting BOTH tracks:** In the dual-track model, if deterministic validation favors one track, only restart the other. Restarting both wastes compute and doesn't leverage the validation signal.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Stage output comparison | Custom diff logic per data type | Extend existing `SchemaValidator` + `ConsensusJudge` patterns | Already has column checks, row counts, CDISC terminology, referential integrity. Add numeric tolerance comparison. |
| Resolution hint formatting | Free-text prompt construction | Structured Jinja2 template for resolution hints | Existing agent system uses .j2 templates. Resolution hints should follow the same pattern for consistency. |
| Resolution state tracking | Ad-hoc variables | Pydantic model (like existing `PipelineState`) | The codebase consistently uses Pydantic for state. Resolution state (iteration count, hint history, comparison results) should follow suit. |
| Docker isolation between tracks | New Docker configuration | Existing `RExecutor` with separate `work_dir` per track | Each track already gets its own directory tree. Docker volumes are already isolated by path. No changes needed. |
| Parallel execution | New concurrency framework | Existing `asyncio.gather()` pattern | Already proven in current `_run_track_a` / `_run_track_b` parallel execution. |

## Common Pitfalls

### Pitfall 1: Prompt Template Divergence Between Tracks
**What goes wrong:** If Track B uses different prompt templates than Track A, the two tracks may be solving slightly different problems, making comparison meaningless.
**Why it happens:** Temptation to create "track_b_sdtm.j2" with OpenAI-specific wording.
**How to avoid:** Both tracks MUST use the exact same prompt templates. The agents are parameterized by LLM adapter, not by prompt content. Model-specific tuning (if needed) should be done via temperature or system prompt prefix, not by changing the task specification.
**Warning signs:** Creating new .j2 files for Track B. Any Track B-specific agent class beyond what the base class provides.

### Pitfall 2: Breaking Track Isolation During Resolution
**What goes wrong:** During resolution, sharing too much of one track's output with the other, causing the "corrected" track to simply copy the other's approach instead of independently validating.
**Why it happens:** Natural instinct to show the failing track what the "right answer" looks like.
**How to avoid:** Resolution hints should describe the DISCREPANCY (what disagrees and by how much), not provide the other track's output. The hint should say "Your DM.csv has 298 rows but 300 subjects are expected" NOT "Here is the other track's DM.csv, make yours match."
**Warning signs:** Hint prompts that include raw data from the other track. Post-resolution outputs that are character-for-character identical.

### Pitfall 3: Infinite Resolution Loops
**What goes wrong:** The resolution loop keeps iterating because the two LLMs persistently disagree on a legitimate ambiguity in the specification.
**Why it happens:** Some disagreements are not bugs but legitimate interpretation differences (e.g., how to handle a subject with all-NA SBP values). No amount of hinting will resolve a specification ambiguity.
**How to avoid:** Hard limit of 2 resolution iterations. After that, use deterministic validation to pick a winner or HALT. Also, before entering resolution, check if the discrepancy is within an "acceptable tolerance" range. Not all disagreements need resolution.
**Warning signs:** Resolution iteration count reaching max on the same stage repeatedly across runs. This indicates a prompt/specification issue, not a code issue.

### Pitfall 4: Cost Explosion from Symmetric Tracks + Resolution
**What goes wrong:** Doubling the full pipeline for Track B roughly doubles LLM API costs. Adding resolution iterations on top can 3-4x the cost.
**Why it happens:** Each pipeline stage involves an LLM call (prompt + generated R code). With 3 stages x 2 tracks = 6 LLM calls minimum (vs. 4 currently: 3 Track A stages + 1 Track B). Plus resolution adds more.
**How to avoid:**
  - Accept the cost increase as the price of validation (this IS the point of double programming)
  - Use temperature=0.0 for both tracks (already configured) to maximize reproducibility
  - Cache generated scripts (already implemented via `ScriptCache`) to avoid redundant calls on re-runs
  - Limit resolution to 2 iterations max
  - Consider making resolution opt-in via config flag for development vs. production runs
**Cost estimate:** See Cost Analysis section below.

### Pitfall 5: Schema Validation Gaps for Track B
**What goes wrong:** Track B now produces SDTM and ADaM outputs that need schema validation, but current `SchemaValidator.validate_track_b()` only validates the old `validation.json` format.
**Why it happens:** Track B's validator was designed for the simplified single-stage output.
**How to avoid:** Track B's output goes through the SAME `SchemaValidator.validate_sdtm()`, `validate_adam()`, and `validate_stats()` calls as Track A. The existing validators are track-agnostic (they take a directory path). `validate_track_b()` becomes deprecated along with `DoubleProgrammerAgent`.
**Warning signs:** Track B-specific validation code. Any validator that checks for `validation.json`.

### Pitfall 6: Script Cache Key Collisions Between Tracks
**What goes wrong:** The current `ScriptCache.cache_key(trial_config, agent_name)` doesn't include the track identifier. If Track A's SDTM script is cached, Track B's SDTM stage might hit the same cache key and use Track A's script (generated by Gemini) with OpenAI.
**Why it happens:** Cache key is `(trial, agent_name)` without track/LLM differentiation.
**How to avoid:** Include the track identifier (or LLM provider name) in the cache key: `ScriptCache.cache_key(trial_config, agent_name, track_id="track_b")`.
**Warning signs:** Track B producing identical R scripts to Track A. Suspiciously fast Track B execution on re-runs.

## Code Examples

### Example 1: Generic Track Runner
```python
# Refactored from _run_track_a -- parameterized by track_id and llm
async def _run_track(
    self,
    track_id: str,       # "track_a" or "track_b"
    llm: BaseLLM,        # GeminiAdapter or OpenAIAdapter
    raw_dir: Path,
    output_dir: Path,
    prompt_dir: Path,
    state: PipelineState,
    state_path: Path,
) -> TrackResult:
    """Run full SDTM -> ADaM -> Stats pipeline for one track."""
    track_dir = output_dir / track_id

    # --- SDTM ---
    sdtm_dir = track_dir / "sdtm"
    sdtm_dir.mkdir(parents=True, exist_ok=True)
    sdtm_agent = SDTMAgent(
        llm=llm, prompt_dir=prompt_dir, trial_config=self.settings.trial
    )
    if self.callback:
        self.callback.on_step_start(f"sdtm_{track_id}", "SDTMAgent", track_id)
    _stdout, sdtm_attempts = await self._run_agent(
        agent=sdtm_agent,
        context={
            "input_path": "/workspace/input/SBPdata.csv",
            "output_dir": "/workspace",
        },
        work_dir=sdtm_dir,
        input_volumes={str(raw_dir): "/workspace/input"},
        expected_inputs=["/workspace/input/SBPdata.csv"],
        expected_outputs=["DM.csv", "VS.csv"],
    )
    SchemaValidator.validate_sdtm(sdtm_dir, self.settings.trial.n_subjects)

    # --- ADaM ---
    adam_dir = track_dir / "adam"
    adam_dir.mkdir(parents=True, exist_ok=True)
    adam_agent = ADaMAgent(
        llm=llm, prompt_dir=prompt_dir, trial_config=self.settings.trial
    )
    _stdout, adam_attempts = await self._run_agent(
        agent=adam_agent,
        context={
            "input_dir": "/workspace/input",
            "output_dir": "/workspace",
        },
        work_dir=adam_dir,
        input_volumes={str(sdtm_dir): "/workspace/input"},
        expected_inputs=["DM.csv", "VS.csv"],
        expected_outputs=["ADTTE.rds", "ADTTE_summary.json"],
    )
    SchemaValidator.validate_adam(adam_dir, self.settings.trial.n_subjects)

    # --- Stats ---
    stats_dir = track_dir / "stats"
    stats_dir.mkdir(parents=True, exist_ok=True)
    stats_agent = StatsAgent(
        llm=llm, prompt_dir=prompt_dir, trial_config=self.settings.trial
    )
    _stdout, stats_attempts = await self._run_agent(
        agent=stats_agent,
        context={
            "adam_dir": "/workspace/adam",
            "sdtm_dir": "/workspace/sdtm",
            "output_dir": "/workspace",
        },
        work_dir=stats_dir,
        input_volumes={
            str(adam_dir): "/workspace/adam",
            str(sdtm_dir): "/workspace/sdtm",
        },
        expected_inputs=["ADTTE.rds", "DM.csv"],
        expected_outputs=["results.json", "km_plot.png"],
    )
    SchemaValidator.validate_stats(stats_dir)

    return TrackResult(
        track_id=track_id,
        sdtm_dir=sdtm_dir,
        adam_dir=adam_dir,
        stats_dir=stats_dir,
        results_path=stats_dir / "results.json",
    )
```

### Example 2: Stage-by-Stage Comparator
```python
class StageComparator:
    """Compare outputs at each pipeline stage between two tracks."""

    @classmethod
    def compare_sdtm(
        cls, track_a_dir: Path, track_b_dir: Path, expected_subjects: int
    ) -> StageComparison:
        """Compare SDTM outputs (DM.csv, VS.csv) between tracks.

        Checks:
        - Row counts match
        - Column sets match
        - Subject IDs match (set equality)
        - Demographics distribution match (ARM, SEX, RACE counts)
        - CDISC terminology compliance (both tracks)
        """
        issues = []

        # Read both tracks' DM.csv
        dm_a = cls._read_csv(track_a_dir / "DM.csv")
        dm_b = cls._read_csv(track_b_dir / "DM.csv")

        # Row count comparison
        if len(dm_a) != len(dm_b):
            issues.append(
                f"DM row count: track_a={len(dm_a)}, track_b={len(dm_b)}"
            )

        # Subject ID set comparison
        ids_a = {row["USUBJID"] for row in dm_a}
        ids_b = {row["USUBJID"] for row in dm_b}
        if ids_a != ids_b:
            only_a = ids_a - ids_b
            only_b = ids_b - ids_a
            issues.append(
                f"Subject ID mismatch: {len(only_a)} only in A, {len(only_b)} only in B"
            )

        # ARM distribution comparison
        arm_a = Counter(row["ARM"] for row in dm_a)
        arm_b = Counter(row["ARM"] for row in dm_b)
        if arm_a != arm_b:
            issues.append(f"ARM distribution: A={dict(arm_a)}, B={dict(arm_b)}")

        # ... similar for VS.csv

        return StageComparison(
            stage="sdtm",
            matches=len(issues) == 0,
            issues=issues,
            track_a_summary={"dm_rows": len(dm_a), "vs_rows": len(vs_a)},
            track_b_summary={"dm_rows": len(dm_b), "vs_rows": len(vs_b)},
        )

    @classmethod
    def compare_adam(
        cls, track_a_dir: Path, track_b_dir: Path, expected_subjects: int
    ) -> StageComparison:
        """Compare ADaM outputs (ADTTE_summary.json) between tracks.

        Checks:
        - n_rows match
        - n_events match (exact)
        - n_censored match (exact)
        - PARAMCD match
        - Column sets match
        """
        ...

    @classmethod
    def compare_stats(
        cls, track_a_dir: Path, track_b_dir: Path
    ) -> StageComparison:
        """Compare Stats outputs (results.json) between tracks.

        Uses the SAME tolerances as existing ConsensusJudge:
        - logrank_p: absolute tolerance 1e-3
        - cox_hr: relative tolerance 0.1%
        - km_median: absolute tolerance 0.5
        - n_subjects, n_events, n_censored: exact match
        """
        ...
```

### Example 3: Resolution Loop
```python
class ResolutionLoop:
    """Orchestrate adversarial resolution when tracks disagree."""

    MAX_ITERATIONS = 2

    async def resolve(
        self,
        disagreement: StageComparison,
        track_a_result: TrackResult,
        track_b_result: TrackResult,
        orchestrator: "PipelineOrchestrator",
    ) -> ResolutionResult:
        """Attempt to resolve a stage-level disagreement.

        Protocol:
        1. Diagnose which track is more likely wrong (deterministic rules)
        2. Generate hint for the failing track
        3. Re-run failing track from the disagreeing stage
        4. Re-compare
        5. If still disagreeing after MAX_ITERATIONS, HALT or use best track
        """
        for iteration in range(1, self.MAX_ITERATIONS + 1):
            # Diagnose: which track failed?
            failing_track = self._diagnose(disagreement)

            # Generate hint (structured, not full output sharing)
            hint = self._generate_hint(disagreement, failing_track)

            # Re-run the failing track from the disagreeing stage
            new_result = await self._rerun_from_stage(
                failing_track,
                disagreement.stage,
                hint,
                orchestrator,
            )

            # Re-compare
            new_comparison = StageComparator.compare_stage(
                disagreement.stage,
                track_a_result if failing_track == "track_b" else new_result,
                track_b_result if failing_track == "track_a" else new_result,
            )

            if new_comparison.matches:
                return ResolutionResult(
                    resolved=True,
                    iterations=iteration,
                    winning_track=None,  # Both now agree
                )

            disagreement = new_comparison  # Update for next iteration

        # Max iterations reached -- pick best track or HALT
        return ResolutionResult(
            resolved=False,
            iterations=self.MAX_ITERATIONS,
            winning_track=self._pick_best_track(disagreement),
        )
```

### Example 4: Resolution Hint Structure
```python
# Resolution hint injected into agent context for re-run
hint_context = {
    "input_path": "/workspace/input/SBPdata.csv",
    "output_dir": "/workspace",
    # Resolution-specific context:
    "resolution_hint": (
        "Your previous output for the SDTM stage had a discrepancy "
        "with an independent validation:\n"
        "- DM.csv: You produced 298 rows, but 300 subjects are expected.\n"
        "- VS.csv: You produced 7748 rows, but 7800 are expected (300 subjects x 26 visits).\n"
        "- 2 subjects appear to have been dropped during deduplication.\n\n"
        "Please check your deduplication logic. Every subject in the raw "
        "data must appear exactly once in DM.csv. Use distinct(USUBJID, .keep_all=TRUE) "
        "to avoid dropping subjects."
    ),
    "attempt_number": 1,  # Resolution attempt, not code retry attempt
}
```

## Stage-by-Stage Comparison Specification

### SDTM Stage Comparison
| Check | Type | Tolerance | Rationale |
|-------|------|-----------|-----------|
| DM row count | Exact | 0 | Both tracks read same raw data, must produce same subject count |
| VS row count | Exact | 0 | n_subjects x n_visits is deterministic |
| Subject ID set | Set equality | 0 | Same subjects in same raw data |
| ARM distribution | Exact per arm | 0 | ARM comes directly from raw data |
| RACE distribution | Exact per category | 0 | Controlled terminology mapping is deterministic |
| SEX distribution | Exact per category | 0 | Direct pass-through from raw data |
| Column names | Set equality | 0 | Both follow same CDISC spec in prompt |

### ADaM Stage Comparison
| Check | Type | Tolerance | Rationale |
|-------|------|-----------|-----------|
| n_rows (subjects) | Exact | 0 | All subjects from SDTM must flow through |
| n_events | Exact | 0 | Event definition is deterministic (SBP < 120) |
| n_censored | Exact | 0 | n_subjects - n_events |
| PARAMCD | Exact | n/a | Must be "TTESB120" per spec |
| Column set | Set equality | 0 | Both follow same ADaM spec |

### Stats Stage Comparison
| Check | Type | Tolerance | Rationale |
|-------|------|-----------|-----------|
| n_subjects | Exact | 0 | Structural agreement required |
| n_events | Exact | 0 | Structural agreement required |
| n_censored | Exact | 0 | Structural agreement required |
| logrank_p | Absolute | 1e-3 | Statistical computation may vary slightly due to floating-point |
| cox_hr | Relative | 0.1% | Same data + same model spec should give very close HR |
| km_median_treatment | Absolute | 0.5 | KM estimation can vary by method |
| km_median_placebo | Absolute | 0.5 | KM estimation can vary by method |

**Key insight:** SDTM and ADaM stages should match EXACTLY (no tolerance) because they are deterministic data transformations. Stats stage gets tolerance because statistical computation involves floating-point arithmetic that may differ between R implementations triggered by different LLMs.

## Cost Analysis

### Current Cost Per Run (Asymmetric)
| Stage | LLM | Approx Tokens (in/out) | Cost |
|-------|-----|----------------------|------|
| Simulator | Gemini 2.5 Pro | ~2K/4K | ~$0.04 |
| SDTM | Gemini 2.5 Pro | ~3K/6K | ~$0.06 |
| ADaM | Gemini 2.5 Pro | ~3K/6K | ~$0.06 |
| Stats | Gemini 2.5 Pro | ~4K/8K | ~$0.08 |
| Double Programmer | GPT-4o | ~3K/6K | ~$0.11 |
| Medical Writer | Gemini 2.5 Pro | ~5K/8K | ~$0.09 |
| **Total** | | | **~$0.44** |

### New Cost Per Run (Symmetric, No Resolution)
| Stage | Track A (Gemini) | Track B (GPT-4o) | Combined |
|-------|-----------------|------------------|----------|
| Simulator | ~$0.04 | - | $0.04 |
| SDTM | ~$0.06 | ~$0.11 | $0.17 |
| ADaM | ~$0.06 | ~$0.11 | $0.17 |
| Stats | ~$0.08 | ~$0.17 | $0.25 |
| Medical Writer | ~$0.09 | - | $0.09 |
| **Total** | | | **~$0.72** |

### With Resolution (worst case: 2 iterations, 1 stage re-run each)
| Scenario | Additional Cost | Total |
|----------|----------------|-------|
| No resolution needed | $0 | ~$0.72 |
| 1 stage re-run, 1 iteration | ~$0.11-0.17 | ~$0.85 |
| 1 stage re-run, 2 iterations | ~$0.22-0.34 | ~$1.00 |
| All stages re-run, 2 iterations (pathological) | ~$0.66-1.02 | ~$1.40-1.74 |

**Assessment:** Cost increase is ~64% for the base case (no resolution). This is the expected cost of genuine double programming. For clinical trial validation, this is trivially small compared to the cost of undetected errors. The resolution loop adds cost only when needed, and is bounded.

**Confidence:** MEDIUM -- token estimates are rough based on prompt template lengths. Actual costs depend on R code length generated by each model.

## Resolution Protocol Design

### Diagnosis: How to Determine Which Track is Wrong

**Priority order of diagnostic signals (deterministic first):**

1. **Schema validation score:** If one track's output fails more schema checks (missing columns, wrong row counts, invalid CDISC terminology), it is more likely wrong.
2. **Referential integrity:** If one track drops subjects (DM has fewer rows than expected), it is more likely wrong.
3. **Value range plausibility:** If one track produces statistically impossible values (p-value > 1, negative HR, more events than subjects), it is more likely wrong.
4. **Consistency with raw data:** If one track's subject count doesn't match the raw data's subject count, it is wrong.
5. **Prior stage agreement:** If tracks agreed at the SDTM stage but disagree at ADaM, and one track's ADaM doesn't match its own SDTM (e.g., different subject count), that track is wrong.

**When diagnosis is ambiguous:** If deterministic rules can't identify the failing track (both are schema-valid, both have plausible values, but they disagree on numeric results), re-run BOTH tracks for that stage. This should be rare.

### Hint Structure

Hints should be structured, not free-text, to prevent hallucination in the hint itself:

```python
@dataclass
class ResolutionHint:
    """Structured hint for a track that needs to re-derive a stage."""

    stage: str                        # "sdtm", "adam", or "stats"
    discrepancies: list[str]          # Human-readable list of what disagrees
    validation_failures: list[str]    # Schema/referential integrity failures
    suggested_checks: list[str]       # Specific things to verify in code

    def to_prompt_text(self) -> str:
        """Render hint as text for injection into agent prompt."""
        lines = [
            f"RESOLUTION HINT: Your previous {self.stage.upper()} output had "
            f"discrepancies with an independent validation.",
            "",
            "Discrepancies found:",
        ]
        for d in self.discrepancies:
            lines.append(f"  - {d}")

        if self.validation_failures:
            lines.append("")
            lines.append("Validation failures:")
            for v in self.validation_failures:
                lines.append(f"  - {v}")

        lines.append("")
        lines.append("Please check:")
        for s in self.suggested_checks:
            lines.append(f"  - {s}")

        return "\n".join(lines)
```

### Resolution Termination

| Condition | Action |
|-----------|--------|
| Tracks agree after re-run | Resolution SUCCESS, proceed with agreed values |
| Max iterations (2) reached, one track has better validation score | Use the better-validated track's output, WARNING verdict |
| Max iterations reached, both equally valid but different values | HALT with diagnostic report for human review |
| Resolution re-run itself crashes (Layer 1 retry exhausted) | HALT with error report |

## State of the Art

| Old Approach (Current) | New Approach (Proposed) | Impact |
|------------------------|------------------------|--------|
| Asymmetric tracks: Track A full pipeline, Track B simplified | Symmetric tracks: both run full SDTM -> ADaM -> Stats | Complete independent validation at every stage |
| Final-only comparison: compare results.json vs validation.json | Stage-by-stage comparison: compare at SDTM, ADaM, and Stats | Pinpoints WHERE divergence occurs |
| Binary verdict: PASS or HALT | Graduated verdict with resolution: PASS -> resolve if needed -> WARNING/HALT | Reduces false HALTs, recovers from single-track errors |
| No resolution: disagreement = pipeline failure | Bounded resolution loop: re-run failing track with hints | Higher success rate, fewer human interventions |
| Track B uses different prompt (double_programmer.j2) | Both tracks use same prompts (sdtm.j2, adam.j2, stats.j2) | True N-version programming: same spec, different implementations |

**Deprecated/outdated after this phase:**
- `DoubleProgrammerAgent` class
- `double_programmer.j2` prompt template
- `SchemaValidator.validate_track_b()` method
- `validation.json` output format
- Single-stage Track B execution

## Open Questions

Things that need user input or could not be fully resolved:

1. **Should resolution be opt-in or always-on?**
   - What we know: Resolution adds cost and complexity. In development/testing, you may want to see disagreements immediately rather than auto-resolving.
   - What's unclear: Is there a config toggle desired? (e.g., `resolution.enabled: true/false` in YAML config)
   - Recommendation: Default to enabled, with config flag to disable.

2. **How should the Medical Writer handle resolution metadata?**
   - What we know: Currently Medical Writer reads `verdict.json`. With resolution, there's additional context (which stages disagreed, how they were resolved).
   - What's unclear: Should the Clinical Study Report mention that resolution was performed? Regulatory implications?
   - Recommendation: Include resolution status in verdict.json, let Medical Writer report it if present. Defer detailed regulatory formatting to a later phase.

3. **Should Track B prompt templates have any model-specific tuning?**
   - What we know: Both tracks should use the same task specification. However, GPT-4o and Gemini 2.5 Pro may respond differently to the same prompts. GPT-4o might need slightly different R code style guidance.
   - What's unclear: Whether current prompts work equally well for both models without modification.
   - Recommendation: Start with identical prompts. If Track B consistently fails at a specific stage, add model-specific system prompt prefixes (not different task specs) as a targeted fix. Test this empirically.

4. **Callback/display changes for symmetric tracks**
   - What we know: Current `ProgressCallback` uses step names like "sdtm", "adam", "stats", "double_programmer". With symmetric tracks, we need "sdtm_track_a", "sdtm_track_b", etc. Plus resolution events.
   - What's unclear: Exact display format. The Rich display module would need updating.
   - Recommendation: This is a follow-up concern for the display layer. The orchestrator should emit track-qualified step names and resolution events via existing callback interface. Display changes can be deferred or handled as a sub-task.

5. **What happens when one track completes and the other crashes entirely?**
   - What we know: Currently `asyncio.gather()` raises if either task fails. With symmetric tracks, if Track A succeeds but Track B crashes (all 3 retries exhausted), the pipeline fails even though one track has valid results.
   - What's unclear: Should the pipeline proceed with single-track results in this case? Or always require both tracks?
   - Recommendation: Default to requiring both tracks (fail if either crashes). Add a config option for "single-track fallback" mode that proceeds with WARNING if one track fails but the other succeeds. This preserves the double-programming integrity while allowing graceful degradation.

## Sources

### Primary (HIGH confidence)
- Codebase analysis: Full read of `orchestrator.py`, `consensus.py`, `retry.py`, `double_programmer.py`, `sdtm.py`, `adam.py`, `stats.py`, `base.py`, `schema_validator.py`, `r_executor.py`, all models, all LLM adapters, all prompt templates
- Python asyncio documentation: `asyncio.Barrier`, `asyncio.gather()` synchronization patterns

### Secondary (MEDIUM confidence)
- [Du et al. (2024) "Improving Factuality and Reasoning in Language Models through Multiagent Debate"](https://arxiv.org/abs/2305.14325) -- ICML 2024. Multi-agent debate protocol: 3 agents, 2 rounds, peer-to-peer response sharing. Key finding: diminishing returns after 2-3 rounds.
- [D3: Debate, Deliberate, Decide](https://arxiv.org/abs/2410.04663) -- Cost-aware adversarial framework with role-specialized agents (advocates, judge, jury) and budgeted stopping.
- [LLM Output Drift: Cross-Provider Validation](https://arxiv.org/abs/2511.07585) -- Structured tasks (SQL, JSON) maintain 100% consistency at temperature=0.0. RAG/creative tasks show 25-75% drift. Key insight: deterministic outputs remain stable across providers.
- [N-Version Programming (Wikipedia)](https://en.wikipedia.org/wiki/N-version_programming) -- Classic fault tolerance pattern: independently developed programs from same spec, comparison via c-vectors at synchronization points. Dual programming used in Airbus A310 flight control.
- [Multi-LLM-Agents Debate (ICLR 2025 Blogpost)](https://d2jud02ci9yv69.cloudfront.net/2025-04-28-mad-159/blog/mad/) -- MAD methods fail to consistently outperform single-agent with increased compute. S2-MAD cuts token costs by 94.5% with <2% accuracy loss via redundancy filtering.
- [Clinical trial double programming practices](https://www.clinicaltechleader.com/doc/is-double-programming-really-required-for-validation-0001) -- Traditional pharma practice of two programmers independently coding from same spec. 80% of SDTM domains standardizable. Not a regulatory requirement but industry standard.
- [Aegean: Consensus Protocol for Reasoning Agents](https://arxiv.org/abs/2512.20184) -- Quorum-based consensus with early termination. 1.2-20x latency reduction vs baselines.
- [Gemini API Pricing](https://ai.google.dev/gemini-api/docs/pricing) -- Gemini 2.5 Pro: $1.25/M input, $10/M output tokens
- [GPT-4o Pricing](https://intuitionlabs.ai/articles/ai-api-pricing-comparison-grok-gemini-openai-claude) -- GPT-4o: $5/M input, $15/M output (or reduced $3/$10)

### Tertiary (LOW confidence)
- Multi-agent debate optimal round counts (from ICLR 2025 blogpost, not verified with primary source): "no obvious trends in performance concerning more agents or more debating rounds" -- this contradicts Du et al. who showed improvement with rounds. Likely task-dependent.

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH -- based on direct codebase analysis. No new libraries needed.
- Architecture (symmetric tracks): HIGH -- existing agent classes are already parameterized by LLM. Refactor is mechanical.
- Architecture (stage comparison): HIGH -- extends existing ConsensusJudge pattern with known tolerance values.
- Architecture (resolution protocol): MEDIUM -- novel component. Design is informed by N-version programming and multi-agent debate research, but specific implementation details (hint formatting, diagnosis logic) need empirical validation.
- Cost analysis: MEDIUM -- token estimates are approximate. Need actual run data to calibrate.
- Pitfalls: HIGH -- based on direct codebase analysis and clinical trial double programming practices.

**Research date:** 2026-02-11
**Valid until:** 2026-03-11 (30 days -- stable domain, no fast-moving dependencies)
