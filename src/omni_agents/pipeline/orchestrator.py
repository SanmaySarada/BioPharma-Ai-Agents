"""Pipeline orchestrator wiring agents to Docker execution.

Runs the full pipeline: Simulator -> fork(Track A, Track B) ->
StageComparator + ResolutionLoop -> Medical Writer, with schema validation
gates and pre-execution R code checks between each agent handoff.

Both tracks run the same SDTM -> ADaM -> Stats pipeline independently via a
generic ``_run_track`` method.  Track A uses Gemini; Track B uses GPT-4 for
model diversity.  After both tracks complete in parallel, StageComparator
compares outputs at every stage post-hoc (Strategy C from research -- not
stage-gated barriers).  When disagreement is detected, the ResolutionLoop
diagnoses the failing track, generates targeted hints, and retries with
cascading downstream re-runs.
"""

import asyncio
import csv
import json
import time
from datetime import UTC, datetime
from pathlib import Path

from loguru import logger
from rich.console import Console

from omni_agents.agents.adam import ADaMAgent
from omni_agents.agents.base import BaseAgent
from omni_agents.agents.medical_writer import MedicalWriterAgent
from omni_agents.agents.sdtm import SDTMAgent
from omni_agents.agents.simulator import SimulatorAgent
from omni_agents.agents.stats import StatsAgent
from omni_agents.config import Settings
from omni_agents.display.callbacks import ProgressCallback
from omni_agents.docker.engine import DockerEngine
from omni_agents.docker.r_executor import RExecutor
from omni_agents.llm.base import BaseLLM
from omni_agents.llm.gemini import GeminiAdapter
from omni_agents.llm.openai_adapter import OpenAIAdapter
from omni_agents.models.consensus import ConsensusVerdict, Verdict
from omni_agents.models.resolution import StageComparisonResult, TrackResult
from omni_agents.models.pipeline import PipelineState, StepResult, StepState, StepStatus
from omni_agents.pipeline.consensus import ConsensusHaltError
from omni_agents.pipeline.resolution import ResolutionLoop
from omni_agents.pipeline.stage_comparator import StageComparator
from omni_agents.pipeline.logging import (
    log_agent_complete,
    log_agent_start,
    log_attempt,
    log_llm_call,
    setup_logging,
)
from omni_agents.pipeline.pre_execution import PreExecutionError, check_r_code
from omni_agents.pipeline.retry import (
    MaxRetriesExceededError,
    NonRetriableError,
    execute_with_retry,
)
from omni_agents.pipeline.schema_validator import SchemaValidator
from omni_agents.pipeline.script_cache import ScriptCache


class PipelineOrchestrator:
    """Orchestrates symmetric Track A + Track B parallel pipeline with stage comparison.

    Runs Simulator sequentially (both tracks need the raw data), then forks
    Track A (Gemini: SDTM -> ADaM -> Stats) and Track B (GPT-4: SDTM -> ADaM
    -> Stats) in parallel via ``asyncio.gather()``, using the generic
    ``_run_track`` method.  After both tracks complete, StageComparator
    compares outputs at every stage post-hoc (Strategy C from research).
    When disagreement is detected and resolution is enabled, ResolutionLoop
    diagnoses the failing track, generates hints, and retries with cascading
    downstream re-runs.  On PASS/WARNING, the Medical Writer generates a
    Clinical Study Report (.docx) from stats output and verdict.
    """

    def __init__(
        self,
        settings: Settings,
        callback: ProgressCallback | None = None,
        console: Console | None = None,
    ) -> None:
        self.settings = settings
        self.callback = callback
        self.console = console
        self.engine = DockerEngine()
        self.executor = RExecutor(
            engine=self.engine,
            image=settings.docker.image,
            memory_limit=settings.docker.memory_limit,
            cpu_count=settings.docker.cpu_count,
            timeout=settings.docker.timeout,
            network_disabled=settings.docker.network_disabled,
        )
        self.script_cache = ScriptCache(
            cache_dir=Path(self.settings.output_dir) / ".script_cache"
        )

    async def _run_agent(
        self,
        agent: BaseAgent,
        context: dict,
        work_dir: Path,
        input_volumes: dict[str, str] | None = None,
        expected_inputs: list[str] | None = None,
        expected_outputs: list[str] | None = None,
        track_id: str = "",
    ) -> tuple[str, list]:
        """Run a single agent through the generate-validate-execute-retry loop.

        This is the core helper for all agents. It handles:
        1. Script caching (check cache on first attempt, store on miss)
        2. Pre-execution R code validation (ERRH-05)
        3. Docker execution via execute_with_retry
        4. Logging all attempts

        Args:
            agent: The agent to run.
            context: Agent-specific context dict (paths, etc.)
            work_dir: Output directory (mounted as /workspace rw)
            input_volumes: Read-only input volume mounts
            expected_inputs: File paths the R code should reference (for pre-exec validation)
            expected_outputs: File paths the R code should produce (for pre-exec validation)
            track_id: Track identifier for cache key isolation (e.g. "track_a",
                "track_b"). Defaults to empty string for shared agents.

        Returns:
            Tuple of (stdout, attempts)
        """
        cache_key = ScriptCache.cache_key(self.settings.trial, agent.name, track_id)

        async def generate_code(
            previous_error: str | None, attempt: int
        ) -> str:
            # Fire retry callback when re-generating code after a failure
            if attempt > 1 and previous_error and self.callback:
                self.callback.on_step_retry(agent.name, attempt, 3, previous_error[:200])

            # On first attempt, try cache
            if attempt == 1 and previous_error is None:
                cached = self.script_cache.get(cache_key)
                if cached is not None:
                    log_agent_start(agent.name)
                    logger.info(f"Using cached R script for {agent.name}")
                    return cached

            ctx = context.copy()
            if previous_error:
                ctx = agent.make_retry_context(ctx, previous_error, attempt)

            code, response = await agent.generate_code(ctx)
            code = agent.inject_seed(code, self.settings.trial.seed)

            # Log LLM token counts (CLI-05)
            log_llm_call(
                agent.name, response.model, response.input_tokens, response.output_tokens,
            )
            if self.callback:
                self.callback.on_llm_call(
                    agent.name, response.model, response.input_tokens, response.output_tokens,
                )

            # Pre-execution validation (ERRH-05)
            if expected_inputs or expected_outputs:
                try:
                    check_r_code(
                        code,
                        expected_inputs=expected_inputs or [],
                        expected_outputs=expected_outputs or [],
                    )
                except PreExecutionError as e:
                    logger.warning(
                        f"Pre-execution validation warnings for {agent.name}: {e.issues}"
                    )
                    # Log but don't block -- some warnings may be false positives
                    # (e.g., path embedded differently). The Docker execution will
                    # catch real issues.

            if attempt == 1 and previous_error is None:
                log_agent_start(agent.name)
                self.script_cache.put(cache_key, code)
            return code

        try:
            stdout, attempts = await execute_with_retry(
                generate_code_fn=generate_code,
                executor=self.executor,
                work_dir=work_dir,
                max_attempts=3,
                agent_name=agent.name,
                input_volumes=input_volumes,
            )
        except (NonRetriableError, MaxRetriesExceededError) as e:
            for attempt in e.attempts:
                log_attempt(agent.name, attempt)
            logger.error(f"{agent.name} failed: {e}")
            if self.callback:
                error_class = (
                    e.error_class.value
                    if isinstance(e, NonRetriableError)
                    else "max_retries_exceeded"
                )
                self.callback.on_step_fail(
                    agent.name, error_class, str(e)[:500], "Check logs for details",
                )
            raise

        for attempt in attempts:
            log_attempt(agent.name, attempt)
        log_agent_complete(agent.name, len(attempts), success=True)

        return stdout, attempts

    def _record_step(
        self,
        state: PipelineState,
        state_path: Path,
        name: str,
        agent_type: str,
        track: str,
        attempts: list,
        status: StepStatus = StepStatus.COMPLETED,
    ) -> None:
        """Record a completed agent step in pipeline state and persist to disk."""
        step_results = []
        for attempt in attempts:
            step_results.append(
                StepResult(
                    success=attempt.error_class is None,
                    output=(
                        attempt.docker_result.stdout[:500]
                        if attempt.docker_result
                        else None
                    ),
                    error=(
                        attempt.docker_result.stderr[:500]
                        if attempt.docker_result and attempt.error_class
                        else None
                    ),
                    code=attempt.generated_code[:200],
                    attempt=attempt.attempt_number,
                    duration_seconds=(
                        attempt.docker_result.duration_seconds
                        if attempt.docker_result
                        else 0
                    ),
                )
            )
        state.steps[name] = StepState(
            name=name,
            agent_type=agent_type,
            track=track,
            status=status,
            attempts=step_results,
        )
        state.current_step = name
        state.save(state_path)

    async def _run_track(
        self,
        track_id: str,
        llm: BaseLLM,
        raw_dir: Path,
        output_dir: Path,
        prompt_dir: Path,
        state: PipelineState,
        state_path: Path,
    ) -> TrackResult:
        """Run full SDTM -> ADaM -> Stats pipeline for one track.

        This is the generic track runner: both Track A and Track B execute
        the same agent sequence (SDTMAgent -> ADaMAgent -> StatsAgent) with
        schema validation gates between each stage.  The only differences
        are the ``track_id`` (which qualifies output directories, step names,
        and cache keys) and the ``llm`` adapter.

        Args:
            track_id: Identifier for this track ("track_a" or "track_b").
            llm: LLM adapter for this track's code generation.
            raw_dir: Directory containing raw SBPdata.csv.
            output_dir: Run output directory.
            prompt_dir: Path to prompt templates.
            state: Pipeline state for step recording.
            state_path: Path to pipeline_state.json.

        Returns:
            A :class:`TrackResult` with paths to each stage's output directory
            and the final results.json.
        """
        track_dir = output_dir / track_id

        # === SDTM Agent ===
        sdtm_dir = track_dir / "sdtm"
        sdtm_dir.mkdir(parents=True, exist_ok=True)
        sdtm_agent = SDTMAgent(
            llm=llm, prompt_dir=prompt_dir, trial_config=self.settings.trial
        )
        if self.callback:
            self.callback.on_step_start(f"sdtm_{track_id}", "SDTMAgent", track_id)
        t0 = time.monotonic()
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
            track_id=track_id,
        )
        duration = time.monotonic() - t0
        self._record_step(
            state, state_path, f"sdtm_{track_id}", "SDTMAgent", track_id, sdtm_attempts
        )
        if self.callback:
            self.callback.on_step_complete(f"sdtm_{track_id}", duration, len(sdtm_attempts))
        SchemaValidator.validate_sdtm(sdtm_dir, self.settings.trial.n_subjects)
        logger.info(f"SDTM schema validation passed ({track_id})")

        # === ADaM Agent ===
        adam_dir = track_dir / "adam"
        adam_dir.mkdir(parents=True, exist_ok=True)
        adam_agent = ADaMAgent(
            llm=llm, prompt_dir=prompt_dir, trial_config=self.settings.trial
        )
        if self.callback:
            self.callback.on_step_start(f"adam_{track_id}", "ADaMAgent", track_id)
        t0 = time.monotonic()
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
            track_id=track_id,
        )
        duration = time.monotonic() - t0
        self._record_step(
            state, state_path, f"adam_{track_id}", "ADaMAgent", track_id, adam_attempts
        )
        if self.callback:
            self.callback.on_step_complete(f"adam_{track_id}", duration, len(adam_attempts))
        SchemaValidator.validate_adam(adam_dir, self.settings.trial.n_subjects)
        logger.info(f"ADaM schema validation passed ({track_id})")

        # === Stats Agent ===
        stats_dir = track_dir / "stats"
        stats_dir.mkdir(parents=True, exist_ok=True)
        stats_agent = StatsAgent(
            llm=llm, prompt_dir=prompt_dir, trial_config=self.settings.trial
        )
        if self.callback:
            self.callback.on_step_start(f"stats_{track_id}", "StatsAgent", track_id)
        t0 = time.monotonic()
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
            track_id=track_id,
        )
        duration = time.monotonic() - t0
        self._record_step(
            state, state_path, f"stats_{track_id}", "StatsAgent", track_id, stats_attempts
        )
        if self.callback:
            self.callback.on_step_complete(f"stats_{track_id}", duration, len(stats_attempts))
        SchemaValidator.validate_stats(stats_dir)
        logger.info(f"Stats schema validation passed ({track_id})")

        return TrackResult(
            track_id=track_id,
            sdtm_dir=sdtm_dir,
            adam_dir=adam_dir,
            stats_dir=stats_dir,
            results_path=stats_dir / "results.json",
        )

    async def run(self) -> Path:
        """Execute the full pipeline with symmetric parallel tracks and stage comparison.

        Flow: Simulator -> fork(Track A via _run_track, Track B via _run_track)
        -> StageComparator (post-hoc, Strategy C) -> ResolutionLoop (if
        disagreement) -> Medical Writer.

        Both tracks run the full SDTM -> ADaM -> Stats pipeline independently
        in parallel.  After both complete, StageComparator compares outputs at
        every stage.  Disagreements trigger the ResolutionLoop which diagnoses
        the failing track, generates targeted hints, and retries with cascading
        downstream re-runs.

        Returns:
            Path to the run output directory.
        """
        pipeline_start = time.monotonic()

        # 1. Create run directory with timestamp
        run_id = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_dir = Path(self.settings.output_dir) / run_id
        raw_dir = output_dir / "raw"
        raw_dir.mkdir(parents=True, exist_ok=True)
        logs_dir = output_dir / "logs"
        logs_dir.mkdir(parents=True, exist_ok=True)

        # 2. Setup logging (route through shared Rich Console if provided)
        setup_logging(logs_dir, run_id, console=self.console)
        logger.info(f"Pipeline started: run_id={run_id}")

        # Initialize pipeline state (PIPE-05)
        state = PipelineState(
            run_id=run_id,
            started_at=datetime.now(tz=UTC),
        )
        state_path = output_dir / "pipeline_state.json"
        state.save(state_path)  # Initial save with empty steps

        # 3. Ensure Docker image is available
        self.engine.ensure_image(
            self.settings.docker.image,
            dockerfile_path=Path("docker/r-clinical"),
        )

        # 4. Create LLM adapters and prompt directory
        gemini = GeminiAdapter(self.settings.llm.gemini)
        prompt_dir = Path(__file__).parent.parent / "templates" / "prompts"

        # === Step 1: Simulator (sequential -- both tracks need raw data) ===
        simulator = SimulatorAgent(
            llm=gemini, prompt_dir=prompt_dir, trial_config=self.settings.trial
        )
        if self.callback:
            self.callback.on_step_start("simulator", "SimulatorAgent", "shared")
        t0 = time.monotonic()
        _stdout, sim_attempts = await self._run_agent(
            agent=simulator,
            context={"output_path": "/workspace/SBPdata.csv"},
            work_dir=raw_dir,
            expected_outputs=["SBPdata.csv"],
        )
        duration = time.monotonic() - t0
        self._record_step(
            state, state_path, "simulator", "SimulatorAgent", "shared", sim_attempts
        )
        if self.callback:
            self.callback.on_step_complete("simulator", duration, len(sim_attempts))

        # Validate Simulator output (existing validation)
        output_csv = raw_dir / "SBPdata.csv"
        if not output_csv.exists():
            raise FileNotFoundError(
                f"Simulator did not produce expected output: {output_csv}"
            )
        self._validate_simulator_output(output_csv)
        logger.info("Simulator output validated")

        # === Step 2: Fork -- parallel Track A and Track B (PIPE-03) ===
        openai = OpenAIAdapter(self.settings.llm.openai)

        t_start = time.monotonic()
        track_a_result, track_b_result = await asyncio.gather(
            self._run_track(
                "track_a", gemini, raw_dir, output_dir, prompt_dir, state, state_path
            ),
            self._run_track(
                "track_b", openai, raw_dir, output_dir, prompt_dir, state, state_path
            ),
        )
        t_parallel = time.monotonic() - t_start
        logger.info(f"Parallel execution completed in {t_parallel:.1f}s")

        # === Step 3: Stage-by-stage comparison (post-hoc, Strategy C from research) ===
        # Both tracks have completed in parallel. Now compare outputs at every stage.
        # This is NOT stage-gated -- both tracks ran all stages independently.
        consensus_dir = output_dir / "consensus"
        consensus_dir.mkdir(parents=True, exist_ok=True)

        if self.callback:
            self.callback.on_step_start("stage_comparison", "StageComparator", "shared")
        t0 = time.monotonic()

        comparison_result = StageComparator.compare_all_stages(
            track_a_result, track_b_result, self.settings.trial.n_subjects
        )

        # Save stage comparisons
        stage_comparisons_path = consensus_dir / "stage_comparisons.json"
        stage_comparisons_path.write_text(
            comparison_result.model_dump_json(indent=2)
        )

        duration = time.monotonic() - t0
        if self.callback:
            self.callback.on_step_complete("stage_comparison", duration, 1)

        # === Step 3b: Resolution loop (if disagreement detected) ===
        resolution_result = None
        if comparison_result.has_disagreement and self.settings.resolution.enabled:
            first_disagreement = comparison_result.first_disagreement
            logger.warning(
                f"Stage disagreement at {first_disagreement.stage}: "
                f"{first_disagreement.issues}"
            )

            resolution_loop = ResolutionLoop(
                max_iterations=self.settings.resolution.max_iterations
            )

            if self.callback:
                self.callback.on_resolution_start(
                    first_disagreement.stage,
                    1,
                    self.settings.resolution.max_iterations,
                )

            resolution_result = await resolution_loop.resolve(
                disagreement=first_disagreement,
                track_a_result=track_a_result,
                track_b_result=track_b_result,
                orchestrator=self,
                expected_subjects=self.settings.trial.n_subjects,
            )

            if self.callback:
                self.callback.on_resolution_complete(
                    first_disagreement.stage,
                    resolution_result.resolved,
                    resolution_result.iterations,
                )

            # Save resolution log
            resolution_log_path = consensus_dir / "resolution_log.json"
            resolution_log_path.write_text(
                resolution_result.model_dump_json(indent=2)
            )

            if not resolution_result.resolved:
                if resolution_result.winning_track is None:
                    # No winner -- HALT
                    logger.error(
                        "Resolution failed: no winning track. Pipeline HALT."
                    )
                    state.status = "failed"
                    state.save(state_path)
                    raise ConsensusHaltError(
                        ConsensusVerdict(
                            verdict=Verdict.HALT,
                            comparisons=[],
                            boundary_warnings=[],
                            investigation_hints=[
                                f"Stage {first_disagreement.stage} disagreement "
                                f"unresolved after "
                                f"{resolution_result.iterations} resolution "
                                f"iterations. Resolution log: "
                                f"{resolution_result.resolution_log}"
                            ],
                        )
                    )
                else:
                    # Winner chosen but still disagree -- WARNING
                    logger.warning(
                        f"Resolution picked {resolution_result.winning_track} "
                        f"as winner after {resolution_result.iterations} "
                        f"iterations"
                    )

        elif comparison_result.has_disagreement and not self.settings.resolution.enabled:
            # Resolution disabled -- HALT on disagreement
            first_disagreement = comparison_result.first_disagreement
            logger.error(
                f"Stage disagreement at {first_disagreement.stage} and "
                f"resolution is disabled. Pipeline HALT."
            )
            state.status = "failed"
            state.save(state_path)
            raise ConsensusHaltError(
                ConsensusVerdict(
                    verdict=Verdict.HALT,
                    comparisons=[],
                    boundary_warnings=[],
                    investigation_hints=[
                        f"Stage {first_disagreement.stage} disagreement. "
                        f"Resolution disabled. "
                        f"Issues: {first_disagreement.issues}"
                    ],
                )
            )

        # Build verdict for Medical Writer
        if (
            comparison_result.has_disagreement
            and resolution_result
            and resolution_result.winning_track
        ):
            overall_verdict = Verdict.WARNING
            investigation_hints = [
                f"Resolution selected {resolution_result.winning_track} after "
                f"{resolution_result.iterations} iterations at stage "
                f"{resolution_result.stage}"
            ]
        else:
            overall_verdict = Verdict.PASS
            investigation_hints = []

        verdict = ConsensusVerdict(
            verdict=overall_verdict,
            comparisons=[],  # Stage comparisons are in stage_comparisons.json
            boundary_warnings=[],
            investigation_hints=investigation_hints,
        )

        # Save verdict
        verdict_path = consensus_dir / "verdict.json"
        verdict_path.write_text(verdict.model_dump_json(indent=2))
        logger.info(f"Pipeline verdict: {verdict.verdict.value}")

        # Record step state
        state.steps["consensus"] = StepState(
            name="consensus",
            agent_type="StageComparator",
            track="shared",
            status=StepStatus.COMPLETED,
            attempts=[
                StepResult(
                    success=True,
                    output=f"Verdict: {verdict.verdict.value}",
                    attempt=1,
                    duration_seconds=0,
                )
            ],
        )
        state.current_step = "consensus"
        state.save(state_path)

        # Handle HALT verdict
        if verdict.verdict == Verdict.HALT:
            state.status = "failed"
            state.save(state_path)
            raise ConsensusHaltError(verdict)

        # === Step 4: Medical Writer (CSR generation) ===
        csr_dir = output_dir / "csr"
        csr_dir.mkdir(parents=True, exist_ok=True)

        # Use winner's stats for Medical Writer (default Track A)
        if resolution_result and resolution_result.winning_track:
            stats_dir = output_dir / resolution_result.winning_track / "stats"
        else:
            stats_dir = output_dir / "track_a" / "stats"

        writer_agent = MedicalWriterAgent(
            llm=gemini, prompt_dir=prompt_dir, trial_config=self.settings.trial
        )
        if self.callback:
            self.callback.on_step_start("medical_writer", "MedicalWriterAgent", "shared")
        t0 = time.monotonic()
        _stdout, writer_attempts = await self._run_agent(
            agent=writer_agent,
            context={
                "results_path": "/workspace/stats/results.json",
                "verdict_path": "/workspace/consensus/verdict.json",
                "table1_path": "/workspace/stats/table1_demographics.csv",
                "table2_path": "/workspace/stats/table2_km_results.csv",
                "table3_path": "/workspace/stats/table3_cox_results.csv",
                "km_plot_path": "/workspace/stats/km_plot.png",
                "output_dir": "/workspace",
            },
            work_dir=csr_dir,
            input_volumes={
                str(stats_dir): "/workspace/stats",
                str(consensus_dir): "/workspace/consensus",
            },
            expected_outputs=["clinical_study_report.docx"],
        )
        duration = time.monotonic() - t0
        self._record_step(
            state, state_path, "medical_writer", "MedicalWriterAgent",
            "shared", writer_attempts,
        )
        if self.callback:
            self.callback.on_step_complete("medical_writer", duration, len(writer_attempts))

        state.status = "completed"
        state.save(state_path)

        logger.info(f"Pipeline completed: output at {output_dir}")

        if self.callback:
            self.callback.on_pipeline_complete(str(output_dir), time.monotonic() - pipeline_start)

        return output_dir

    def _validate_simulator_output(self, csv_path: Path) -> None:
        """Validate the simulator output CSV has expected structure.

        This is a basic sanity check -- not full CDISC validation.
        Checks column names, row count range, and arm distribution.
        """
        with open(csv_path) as f:
            reader = csv.DictReader(f)
            rows = list(reader)

        # Check columns
        expected_cols = {"USUBJID", "ARM", "AGE", "SEX", "RACE", "VISIT", "SBP"}
        actual_cols = set(rows[0].keys()) if rows else set()
        missing = expected_cols - actual_cols
        if missing:
            msg = f"Missing columns in output: {missing}"
            raise ValueError(msg)

        # Check row count (should be n_subjects * visits)
        expected_rows = self.settings.trial.n_subjects * self.settings.trial.visits
        if len(rows) != expected_rows:
            msg = f"Expected {expected_rows} rows, got {len(rows)}"
            raise ValueError(msg)

        # Check arm distribution
        subjects: dict[str, str] = {}
        for row in rows:
            subjects[row["USUBJID"]] = row["ARM"]
        treatment_count = sum(
            1 for arm in subjects.values() if arm == "Treatment"
        )
        placebo_count = sum(
            1 for arm in subjects.values() if arm == "Placebo"
        )
        total = treatment_count + placebo_count
        if total != self.settings.trial.n_subjects:
            msg = (
                f"Expected {self.settings.trial.n_subjects} subjects, "
                f"got {total}"
            )
            raise ValueError(msg)

        # Check 2:1 ratio (allow +-5 for rounding)
        expected_treatment = self.settings.trial.n_subjects * 2 // 3
        expected_placebo = self.settings.trial.n_subjects - expected_treatment
        if abs(treatment_count - expected_treatment) > 5:
            msg = (
                f"Randomization off: {treatment_count} Treatment, "
                f"{placebo_count} Placebo "
                f"(expected ~{expected_treatment}:{expected_placebo})"
            )
            raise ValueError(msg)

        logger.info(
            f"Output validated: {len(rows)} rows, {total} subjects "
            f"({treatment_count} Treatment, {placebo_count} Placebo)"
        )
