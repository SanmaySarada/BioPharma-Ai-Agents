"""Pipeline orchestrator wiring agents to Docker execution.

Runs the full pipeline: Simulator -> fork(Track A, Track B) -> ConsensusJudge
-> Medical Writer, with schema validation gates and pre-execution R code checks
between each agent handoff.  Track A uses Gemini; Track B uses GPT-4 for model
diversity.
"""

import asyncio
import csv
import json
import time
from datetime import UTC, datetime
from pathlib import Path

from loguru import logger

from omni_agents.agents.adam import ADaMAgent
from omni_agents.agents.base import BaseAgent
from omni_agents.agents.double_programmer import DoubleProgrammerAgent
from omni_agents.agents.medical_writer import MedicalWriterAgent
from omni_agents.agents.sdtm import SDTMAgent
from omni_agents.agents.simulator import SimulatorAgent
from omni_agents.agents.stats import StatsAgent
from omni_agents.config import Settings
from omni_agents.docker.engine import DockerEngine
from omni_agents.docker.r_executor import RExecutor
from omni_agents.llm.gemini import GeminiAdapter
from omni_agents.llm.openai_adapter import OpenAIAdapter
from omni_agents.models.consensus import Verdict
from omni_agents.models.pipeline import PipelineState, StepResult, StepState, StepStatus
from omni_agents.pipeline.consensus import ConsensusHaltError, ConsensusJudge
from omni_agents.pipeline.logging import (
    log_agent_complete,
    log_agent_start,
    log_attempt,
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
    """Orchestrates Track A + Track B parallel pipeline with consensus gating.

    Runs Simulator sequentially (both tracks need the raw data), then forks
    Track A (Gemini: SDTM -> ADaM -> Stats) and Track B (GPT-4: independent
    validation) in parallel via ``asyncio.gather()``.  After both tracks
    complete, the ConsensusJudge compares results and the pipeline proceeds
    (PASS/WARNING) or halts (HALT).  On PASS/WARNING, the Medical Writer
    generates a Clinical Study Report (.docx) from stats output and verdict.
    """

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
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

        Returns:
            Tuple of (stdout, attempts)
        """
        cache_key = ScriptCache.cache_key(self.settings.trial, agent.name)

        async def generate_code(
            previous_error: str | None, attempt: int
        ) -> str:
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

            code, _response = await agent.generate_code(ctx)
            code = agent.inject_seed(code, self.settings.trial.seed)

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

    async def _run_track_a(
        self,
        raw_dir: Path,
        output_dir: Path,
        gemini: GeminiAdapter,
        prompt_dir: Path,
        state: PipelineState,
        state_path: Path,
    ) -> Path:
        """Run Track A pipeline: SDTM -> ADaM -> Stats.

        Args:
            raw_dir: Directory containing raw SBPdata.csv.
            output_dir: Run output directory.
            gemini: GeminiAdapter for Track A LLM calls.
            prompt_dir: Path to prompt templates.
            state: Pipeline state for step recording.
            state_path: Path to pipeline_state.json.

        Returns:
            Path to Track A ``results.json``.
        """
        # === SDTM Agent ===
        sdtm_dir = output_dir / "track_a" / "sdtm"
        sdtm_dir.mkdir(parents=True, exist_ok=True)

        sdtm_agent = SDTMAgent(
            llm=gemini, prompt_dir=prompt_dir, trial_config=self.settings.trial
        )
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
        self._record_step(
            state, state_path, "sdtm", "SDTMAgent", "track_a", sdtm_attempts
        )

        # Validate SDTM output (PIPE-06)
        SchemaValidator.validate_sdtm(sdtm_dir, self.settings.trial.n_subjects)
        logger.info("SDTM schema validation passed")

        # === ADaM Agent ===
        adam_dir = output_dir / "track_a" / "adam"
        adam_dir.mkdir(parents=True, exist_ok=True)

        adam_agent = ADaMAgent(
            llm=gemini, prompt_dir=prompt_dir, trial_config=self.settings.trial
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
        self._record_step(
            state, state_path, "adam", "ADaMAgent", "track_a", adam_attempts
        )

        # Validate ADaM output (PIPE-06)
        SchemaValidator.validate_adam(adam_dir, self.settings.trial.n_subjects)
        logger.info("ADaM schema validation passed")

        # === Stats Agent ===
        stats_dir = output_dir / "track_a" / "stats"
        stats_dir.mkdir(parents=True, exist_ok=True)

        stats_agent = StatsAgent(
            llm=gemini, prompt_dir=prompt_dir, trial_config=self.settings.trial
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
        self._record_step(
            state, state_path, "stats", "StatsAgent", "track_a", stats_attempts
        )

        # Validate Stats output (PIPE-06)
        SchemaValidator.validate_stats(stats_dir)
        logger.info("Stats schema validation passed")

        return stats_dir / "results.json"

    async def _run_track_b(
        self,
        raw_dir: Path,
        output_dir: Path,
        openai: OpenAIAdapter,
        prompt_dir: Path,
        state: PipelineState,
        state_path: Path,
    ) -> Path:
        """Run Track B pipeline: DoubleProgrammerAgent independent validation.

        Track B receives ONLY raw SBPdata.csv -- no access to Track A outputs.
        This enforces isolation (ISOL-01 through ISOL-03).

        Args:
            raw_dir: Directory containing raw SBPdata.csv.
            output_dir: Run output directory.
            openai: OpenAIAdapter for Track B LLM calls.
            prompt_dir: Path to prompt templates.
            state: Pipeline state for step recording.
            state_path: Path to pipeline_state.json.

        Returns:
            Path to Track B ``validation.json``.
        """
        track_b_dir = output_dir / "track_b"
        track_b_dir.mkdir(parents=True, exist_ok=True)

        agent = DoubleProgrammerAgent(
            llm=openai,
            prompt_dir=prompt_dir,
            trial_config=self.settings.trial,
        )
        _stdout, dp_attempts = await self._run_agent(
            agent=agent,
            context={
                "input_path": "/workspace/input/SBPdata.csv",
                "output_dir": "/workspace",
            },
            work_dir=track_b_dir,
            # CRITICAL ISOLATION (ISOL-01, ISOL-02, ISOL-03):
            # Track B only sees raw data. No sdtm_dir, adam_dir, or stats_dir.
            input_volumes={str(raw_dir): "/workspace/input"},
            expected_inputs=["/workspace/input/SBPdata.csv"],
            expected_outputs=["validation.json"],
        )
        self._record_step(
            state,
            state_path,
            "double_programmer",
            "DoubleProgrammerAgent",
            "track_b",
            dp_attempts,
        )

        # Validate Track B output (PIPE-06 for Track B)
        SchemaValidator.validate_track_b(track_b_dir)
        logger.info("Track B schema validation passed")

        return track_b_dir / "validation.json"

    async def run(self) -> Path:
        """Execute the full pipeline with parallel tracks and consensus gate.

        Flow: Simulator -> fork(Track A, Track B) -> ConsensusJudge -> Medical Writer.

        Returns:
            Path to the run output directory.
        """
        # 1. Create run directory with timestamp
        run_id = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_dir = Path(self.settings.output_dir) / run_id
        raw_dir = output_dir / "raw"
        raw_dir.mkdir(parents=True, exist_ok=True)
        logs_dir = output_dir / "logs"
        logs_dir.mkdir(parents=True, exist_ok=True)

        # 2. Setup logging
        setup_logging(logs_dir, run_id)
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
        _stdout, sim_attempts = await self._run_agent(
            agent=simulator,
            context={"output_path": "/workspace/SBPdata.csv"},
            work_dir=raw_dir,
            expected_outputs=["SBPdata.csv"],
        )
        self._record_step(
            state, state_path, "simulator", "SimulatorAgent", "shared", sim_attempts
        )

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
            self._run_track_a(
                raw_dir, output_dir, gemini, prompt_dir, state, state_path
            ),
            self._run_track_b(
                raw_dir, output_dir, openai, prompt_dir, state, state_path
            ),
        )
        t_parallel = time.monotonic() - t_start
        logger.info(f"Parallel execution completed in {t_parallel:.1f}s")

        # === Step 3: Consensus gate (PIPE-04, ISOL-04) ===
        # Create consensus directory ONLY after both tracks complete (ISOL-04)
        consensus_dir = output_dir / "consensus"
        consensus_dir.mkdir(parents=True, exist_ok=True)

        # Run consensus comparison
        verdict = ConsensusJudge.compare(track_a_result, track_b_result)

        # Save verdict to consensus directory
        verdict_path = consensus_dir / "verdict.json"
        verdict_path.write_text(verdict.model_dump_json(indent=2))
        logger.info(f"Consensus verdict: {verdict.verdict.value}")

        # Record consensus step
        state.steps["consensus"] = StepState(
            name="consensus",
            agent_type="ConsensusJudge",
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

        # Handle verdict (PIPE-04)
        if verdict.verdict == Verdict.HALT:
            state.status = "failed"
            state.save(state_path)
            # Save diagnostic report (JUDG-06)
            diag_path = consensus_dir / "diagnostic_report.json"
            diag_path.write_text(
                json.dumps(verdict.to_diagnostic_report(), indent=2)
            )
            logger.error(
                f"CONSENSUS HALT: {verdict.investigation_hints}"
            )
            raise ConsensusHaltError(verdict)

        if verdict.verdict == Verdict.WARNING:
            logger.warning(
                f"CONSENSUS WARNING: proceeding with caution. "
                f"Boundary warnings: {verdict.boundary_warnings}"
            )
            # Pipeline proceeds -- verdict.json in consensus_dir carries the
            # flag for Phase 4 Medical Writer to read (JUDG-05 contract).
            #
            # Phase 4 contract (JUDG-05):
            #   File: {output_dir}/consensus/verdict.json
            #   Key: verdict (string: "PASS", "WARNING", or "HALT")
            #   Key: boundary_warnings (list of strings, may be empty)
            #   Key: comparisons (list of per-metric comparison objects)
            #   Phase 4 should check verdict == "WARNING" and include
            #   boundary_warnings in the report narrative when present.

        # === Step 4: Medical Writer (CSR generation) ===
        csr_dir = output_dir / "csr"
        csr_dir.mkdir(parents=True, exist_ok=True)

        stats_dir = output_dir / "track_a" / "stats"

        writer_agent = MedicalWriterAgent(
            llm=gemini, prompt_dir=prompt_dir, trial_config=self.settings.trial
        )
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
        self._record_step(
            state, state_path, "medical_writer", "MedicalWriterAgent",
            "shared", writer_attempts,
        )

        state.status = "completed"
        state.save(state_path)

        logger.info(f"Pipeline completed: output at {output_dir}")
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
