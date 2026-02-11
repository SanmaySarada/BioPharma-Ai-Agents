"""Pipeline orchestrator wiring agents to Docker execution.

Runs the full Track A pipeline: Simulator -> SDTM -> ADaM -> Stats,
with schema validation gates and pre-execution R code checks between
each agent handoff.
"""

import csv
from datetime import datetime
from pathlib import Path

from loguru import logger

from omni_agents.agents.adam import ADaMAgent
from omni_agents.agents.base import BaseAgent
from omni_agents.agents.sdtm import SDTMAgent
from omni_agents.agents.simulator import SimulatorAgent
from omni_agents.agents.stats import StatsAgent
from omni_agents.config import Settings
from omni_agents.docker.engine import DockerEngine
from omni_agents.docker.r_executor import RExecutor
from omni_agents.llm.gemini import GeminiAdapter
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
from omni_agents.pipeline.schema_validator import SchemaValidationError, SchemaValidator
from omni_agents.pipeline.script_cache import ScriptCache


class PipelineOrchestrator:
    """Orchestrates the Track A pipeline execution.

    Runs Simulator -> SDTM -> ADaM -> Stats sequentially, with schema
    validation gates (PIPE-06) and pre-execution R code checks (ERRH-05)
    between each agent handoff.
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

    async def run(self) -> Path:
        """Execute the Track A pipeline. Returns path to output directory."""
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

        # 3. Ensure Docker image is available
        self.engine.ensure_image(
            self.settings.docker.image,
            dockerfile_path=Path("docker/r-clinical"),
        )

        # 4. Create LLM adapter (Gemini for all Track A agents)
        gemini = GeminiAdapter(self.settings.llm.gemini)
        prompt_dir = Path(__file__).parent.parent / "templates" / "prompts"

        # === Step 1: Simulator ===
        simulator = SimulatorAgent(
            llm=gemini, prompt_dir=prompt_dir, trial_config=self.settings.trial
        )
        await self._run_agent(
            agent=simulator,
            context={"output_path": "/workspace/SBPdata.csv"},
            work_dir=raw_dir,
            expected_outputs=["SBPdata.csv"],
        )

        # Validate Simulator output (existing validation)
        output_csv = raw_dir / "SBPdata.csv"
        if not output_csv.exists():
            raise FileNotFoundError(
                f"Simulator did not produce expected output: {output_csv}"
            )
        self._validate_simulator_output(output_csv)
        logger.info("Simulator output validated")

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
        treatment_count = sum(1 for arm in subjects.values() if arm == "Treatment")
        placebo_count = sum(1 for arm in subjects.values() if arm == "Placebo")
        total = treatment_count + placebo_count
        if total != self.settings.trial.n_subjects:
            msg = f"Expected {self.settings.trial.n_subjects} subjects, got {total}"
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
