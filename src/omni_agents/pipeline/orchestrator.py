"""Pipeline orchestrator wiring agents to Docker execution.

For Phase 1, this runs only the Simulator agent.
Future phases will add the full DAG (SDTM, ADaM, Stats, Track B, Judge, Writer).
"""

import csv
from datetime import datetime
from pathlib import Path

from loguru import logger

from omni_agents.agents.simulator import SimulatorAgent
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
from omni_agents.pipeline.retry import (
    MaxRetriesExceededError,
    NonRetriableError,
    execute_with_retry,
)


class PipelineOrchestrator:
    """Orchestrates the pipeline execution.

    For Phase 1, this runs only the Simulator agent.
    Future phases will add the full DAG (SDTM, ADaM, Stats, Track B, Judge, Writer).
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

    async def run(self) -> Path:
        """Execute the pipeline. Returns path to output directory."""
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

        # 4. Create Simulator agent
        gemini = GeminiAdapter(self.settings.llm.gemini)
        prompt_dir = Path(__file__).parent.parent / "templates" / "prompts"
        simulator = SimulatorAgent(
            llm=gemini,
            prompt_dir=prompt_dir,
            trial_config=self.settings.trial,
        )

        # 5. Define the code generation function for retry loop
        async def generate_simulator_code(
            previous_error: str | None, attempt: int
        ) -> str:
            context: dict = {"output_path": "/workspace/SBPdata.csv"}
            if previous_error:
                context = simulator.make_retry_context(context, previous_error, attempt)

            code, _response = await simulator.generate_code(context)
            # Inject set.seed() -- orchestrator responsibility, not LLM's
            code = simulator.inject_seed(code, self.settings.trial.seed)
            if attempt == 1:
                log_agent_start(simulator.name)
            return code

        # 6. Execute with retry
        try:
            stdout, attempts = await execute_with_retry(
                generate_code_fn=generate_simulator_code,
                executor=self.executor,
                work_dir=raw_dir,
                max_attempts=3,
            )
        except (NonRetriableError, MaxRetriesExceededError) as e:
            for attempt in e.attempts:
                log_attempt(simulator.name, attempt)
            logger.error(f"Simulator failed: {e}")
            raise

        # 7. Log all attempts
        for attempt in attempts:
            log_attempt(simulator.name, attempt)
        log_agent_complete(simulator.name, len(attempts), success=True)

        # 8. Verify output exists
        output_csv = raw_dir / "SBPdata.csv"
        if not output_csv.exists():
            raise FileNotFoundError(
                f"Simulator did not produce expected output: {output_csv}"
            )

        # 9. Basic output validation
        self._validate_simulator_output(output_csv)

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
