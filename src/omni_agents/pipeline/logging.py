"""Structured logging for pipeline execution attempts.

Provides dual-sink logging via loguru:

- **Console sink**: Human-readable, colorized, shows agent name and step.
- **File sink**: JSON-structured JSONL written to ``{log_dir}/{run_id}/pipeline.jsonl``
  for programmatic parsing and audit trails.

Per PITFALLS.md ERRH-04: all attempts (including failures) must be logged
with generated code, error output, and error classification.
"""

import sys
from pathlib import Path

from loguru import logger

from omni_agents.models.execution import AgentAttempt


def setup_logging(log_dir: Path, run_id: str) -> None:
    """Configure loguru sinks for pipeline execution.

    Sets up two sinks:
    1. Console (stderr): human-readable format with agent context.
    2. File: JSON-structured JSONL at ``{log_dir}/{run_id}/pipeline.jsonl``.

    Removes all existing handlers first to avoid duplicate output.

    Args:
        log_dir: Root directory for log storage.
        run_id: Unique identifier for this pipeline run.
    """
    # Remove default handler
    logger.remove()

    # Console: human-readable with agent context
    logger.add(
        sys.stderr,
        format=(
            "<green>{time:HH:mm:ss}</green> | <level>{level: <8}</level>"
            " | <cyan>{extra[agent]}</cyan> | {message}"
        ),
        level="INFO",
        filter=lambda record: "agent" in record["extra"],
    )

    # Console: default handler for non-agent logs
    logger.add(
        sys.stderr,
        format="<green>{time:HH:mm:ss}</green> | <level>{level: <8}</level> | {message}",
        level="INFO",
        filter=lambda record: "agent" not in record["extra"],
    )

    # File: JSON structured
    log_file = log_dir / run_id / "pipeline.jsonl"
    log_file.parent.mkdir(parents=True, exist_ok=True)
    logger.add(
        str(log_file),
        format="{message}",
        serialize=True,
        level="DEBUG",
    )


def log_attempt(agent_name: str, attempt: AgentAttempt) -> None:
    """Log a complete execution attempt record.

    Logs at INFO level for successes, WARNING for failures.
    Always logs generated code at DEBUG level for audit trail.

    Args:
        agent_name: Name of the agent that produced this attempt.
        attempt: The attempt record to log.
    """
    with logger.contextualize(agent=agent_name):
        if attempt.error_class is None:
            logger.info(
                "Attempt {attempt} succeeded in {duration:.1f}s",
                attempt=attempt.attempt_number,
                duration=attempt.docker_result.duration_seconds if attempt.docker_result else 0,
            )
        else:
            logger.warning(
                "Attempt {attempt} failed ({error_class}) in {duration:.1f}s: {error}",
                attempt=attempt.attempt_number,
                error_class=attempt.error_class.value,
                duration=attempt.docker_result.duration_seconds if attempt.docker_result else 0,
                error=attempt.docker_result.stderr[:200] if attempt.docker_result else "no output",
            )

        # Always log the generated code at DEBUG level for audit
        logger.debug(
            "Generated R code (attempt {attempt}):\n{code}",
            attempt=attempt.attempt_number,
            code=attempt.generated_code,
        )


def log_agent_start(agent_name: str) -> None:
    """Log the start of an agent execution.

    Args:
        agent_name: Name of the agent starting execution.
    """
    with logger.contextualize(agent=agent_name):
        logger.info("Agent started")


def log_agent_complete(agent_name: str, total_attempts: int, *, success: bool) -> None:
    """Log the completion of an agent execution.

    Args:
        agent_name: Name of the agent that completed.
        total_attempts: Total number of attempts made.
        success: Whether the agent ultimately succeeded.
    """
    with logger.contextualize(agent=agent_name):
        if success:
            logger.info(
                "Agent completed successfully in {attempts} attempt(s)",
                attempts=total_attempts,
            )
        else:
            logger.error(
                "Agent failed after {attempts} attempt(s)",
                attempts=total_attempts,
            )
