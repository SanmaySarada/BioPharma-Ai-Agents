"""Structured logging for pipeline execution attempts.

Provides dual-sink logging via loguru:

- **Console sink**: Human-readable, colorized, shows agent name and step.
  When a shared Rich ``Console`` is provided, output routes through it to
  avoid corrupting the Rich Live display.
- **File sink**: JSON-structured JSONL written to ``{log_dir}/{run_id}/pipeline.jsonl``
  for programmatic parsing and audit trails.

Per PITFALLS.md ERRH-04: all attempts (including failures) must be logged
with generated code, error output, and error classification.
"""

from __future__ import annotations

import sys
from typing import TYPE_CHECKING

from loguru import logger

if TYPE_CHECKING:
    from pathlib import Path

    from rich.console import Console

    from omni_agents.models.execution import AgentAttempt

# Module-level shared console reference for Rich-based console sink.
_console: Console | None = None


def setup_logging(
    log_dir: Path,
    run_id: str,
    console: Console | None = None,
) -> None:
    """Configure loguru sinks for pipeline execution.

    Sets up console and file sinks:

    - If *console* is provided, a single console sink writes through the
      shared Rich ``Console`` (prevents Live display corruption).
    - If *console* is ``None`` (backward compat), two ``sys.stderr`` sinks
      are configured: one for agent-contextualized logs, one for plain logs.
    - A JSON-structured JSONL file sink is always created.

    Removes all existing handlers first to avoid duplicate output.

    Args:
        log_dir: Root directory for log storage.
        run_id: Unique identifier for this pipeline run.
        console: Optional shared Rich Console for output routing.
    """
    global _console  # noqa: PLW0603
    _console = console

    # Remove default handler
    logger.remove()

    if console is not None:
        # Route ALL console output through the shared Rich Console so loguru
        # does not write directly to stderr (which would corrupt Live display).
        logger.add(
            lambda msg: console.print(msg, end="", highlight=False, markup=False),
            format="{time:HH:mm:ss} | {level: <8} | {message}",
            level="INFO",
            colorize=False,
        )
    else:
        # Legacy mode: two stderr sinks (agent-context and default).

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
            format=(
                "<green>{time:HH:mm:ss}</green> | <level>{level: <8}</level>"
                " | {message}"
            ),
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


def log_llm_call(
    agent_name: str,
    model: str,
    input_tokens: int | None,
    output_tokens: int | None,
) -> None:
    """Log an LLM API call with token counts.

    Ensures token counts appear in both the JSONL file sink (structured)
    and the console sink (human-readable).

    Args:
        agent_name: Name of the agent that made the LLM call.
        model: Model identifier (e.g. ``"gemini-2.0-flash"``).
        input_tokens: Prompt token count, if available.
        output_tokens: Completion token count, if available.
    """
    with logger.contextualize(agent=agent_name):
        logger.info(
            "LLM call: model={model} input_tokens={input_tokens} output_tokens={output_tokens}",
            model=model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
        )
