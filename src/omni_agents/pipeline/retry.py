"""Error-feedback retry loop with error classification for R execution.

Implements the generate-execute-classify-retry loop that makes LLM-generated
R code viable.  Feeding R stderr back to the LLM resolves ~70-80% of code
errors on the first retry.  But not all errors should be retried:

- **Code bugs** (syntax, undefined variables): retried with error feedback
- **Data path errors** (file not found): retried with path context
- **Timeout**: retried (execution may succeed with simpler code)
- **Unknown errors**: retried (best-effort)
- **Environment errors** (missing R package): NOT retried -- needs Docker image fix
- **Statistical errors** (singular matrix, convergence): NOT retried -- needs escalation

Per PITFALLS.md ERRH-02: max 3 retries, classify before retry.
Per PITFALLS.md ERRH-07: don't waste LLM calls on non-retriable errors.
"""

from collections.abc import Callable, Coroutine
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from omni_agents.models.execution import (
    AgentAttempt,
    DockerResult,
    ErrorClassification,
)


class NonRetriableError(Exception):
    """Raised when an error is classified as non-retriable.

    Attributes:
        error_class: The classification that caused the halt.
        attempts: All execution attempts up to and including the failing one.
    """

    def __init__(
        self,
        message: str,
        *,
        error_class: ErrorClassification,
        attempts: list[AgentAttempt],
    ) -> None:
        self.error_class = error_class
        self.attempts = attempts
        super().__init__(message)


class MaxRetriesExceededError(Exception):
    """Raised when all retry attempts are exhausted without success.

    Attributes:
        attempts: All execution attempts.
    """

    def __init__(self, message: str, *, attempts: list[AgentAttempt]) -> None:
        self.attempts = attempts
        super().__init__(message)


def classify_error(stderr: str, exit_code: int, timed_out: bool) -> ErrorClassification:
    """Classify an R execution error for retry decision.

    Implements the error classification decision tree from
    VALIDATION_STRATEGY.md.  Order matters: more specific patterns
    are checked before more general ones.

    Args:
        stderr: The stderr output from the R execution.
        exit_code: The process exit code.
        timed_out: Whether the execution was killed due to timeout.

    Returns:
        The error classification determining retry strategy.
    """
    if timed_out:
        return ErrorClassification.TIMEOUT

    stderr_lower = stderr.lower()

    # Environment errors -- NOT retriable (fix Docker image)
    env_patterns = [
        "there is no package called",
        "cannot open shared object file",
        "unable to load shared object",
    ]
    if any(p in stderr_lower for p in env_patterns):
        return ErrorClassification.ENVIRONMENT_ERROR

    # Data path errors -- retriable with path context
    path_patterns = [
        "cannot open connection",
        "no such file or directory",
        "cannot open file",
    ]
    if any(p in stderr_lower for p in path_patterns):
        return ErrorClassification.DATA_PATH_ERROR

    # Statistical errors -- escalate, don't retry
    stat_patterns = [
        "error in solve.default",
        "singular",
        "convergence",
        "not positive definite",
        "infinite or missing values",
        "na/nan/inf in foreign function call",
    ]
    if any(p in stderr_lower for p in stat_patterns):
        return ErrorClassification.STATISTICAL_ERROR

    # Code bugs -- retriable (syntax errors, object not found, etc.)
    code_patterns = [
        "object",  # "object 'x' not found"
        "unexpected",  # "unexpected symbol"
        "error in",  # Generic R errors
        "could not find",  # Could be function or object
        "subscript out of bounds",
        "non-numeric argument",
        "replacement has",
        "arguments imply differing number of rows",
    ]
    if any(p in stderr_lower for p in code_patterns):
        return ErrorClassification.CODE_BUG

    return ErrorClassification.UNKNOWN


def is_retriable(error_class: ErrorClassification) -> bool:
    """Determine whether an error classification is retriable.

    Returns True for CODE_BUG, DATA_PATH_ERROR, UNKNOWN, TIMEOUT.
    Returns False for ENVIRONMENT_ERROR, STATISTICAL_ERROR.
    """
    return error_class in {
        ErrorClassification.CODE_BUG,
        ErrorClassification.DATA_PATH_ERROR,
        ErrorClassification.UNKNOWN,
        ErrorClassification.TIMEOUT,
    }


# Type alias for the code generation callback.
# (previous_error: str | None, attempt_number: int) -> generated_code: str
GenerateCodeFn = Callable[[str | None, int], Coroutine[Any, Any, str]]


def _is_real_error(stderr: str) -> bool:
    """Check whether stderr contains a real R error (not just warnings).

    R prints warnings to stderr even on successful execution.  Only
    treat the output as a failure if it contains an actual ``Error``
    or ``Error in`` marker that isn't part of a warning message.
    """
    for line in stderr.splitlines():
        stripped = line.strip()
        if stripped.startswith("Error") or stripped.startswith("error"):
            return True
    return False


async def execute_with_retry(
    generate_code_fn: GenerateCodeFn,
    executor: Any,
    work_dir: Path,
    max_attempts: int = 3,
    input_volumes: dict[str, str] | None = None,
) -> tuple[str, list[AgentAttempt]]:
    """Run the generate-execute-classify-retry loop.

    Orchestrates the core retry mechanism:

    1. Call ``generate_code_fn`` to get R code (with error feedback on retries).
    2. Execute the code in Docker via ``executor.execute()``.
    3. On success, return stdout and the list of attempts.
    4. On failure, classify the error and either retry or raise.

    Args:
        generate_code_fn: Async callable ``(previous_error, attempt_number) -> code``.
            The caller (agent) provides this -- it encapsulates prompt construction
            with error feedback.
        executor: ``RExecutor`` instance with an ``execute(code, work_dir, input_volumes)``
            method returning ``DockerResult``.
        work_dir: Path to the workspace directory mounted into Docker.
        max_attempts: Maximum number of attempts (default 3, per ERRH-02).
        input_volumes: Optional dict of additional read-only volume mounts
            ``{host_path: container_path}``.

    Returns:
        Tuple of ``(stdout_output, attempts)`` on success.

    Raises:
        NonRetriableError: If the error is classified as non-retriable
            (ENVIRONMENT_ERROR, STATISTICAL_ERROR).
        MaxRetriesExceededError: If all attempts are exhausted without success.
    """
    attempts: list[AgentAttempt] = []
    last_error: str | None = None

    for attempt_num in range(1, max_attempts + 1):
        # Generate code (with error feedback if retry)
        code = await generate_code_fn(last_error, attempt_num)

        # Execute in Docker
        docker_result: DockerResult = executor.execute(code, work_dir, input_volumes)

        # Check for success: exit_code == 0, not timed out, no real errors in stderr
        if (
            docker_result.exit_code == 0
            and not docker_result.timed_out
            and not _is_real_error(docker_result.stderr)
        ):
            attempt = AgentAttempt(
                attempt_number=attempt_num,
                generated_code=code,
                docker_result=docker_result,
                error_class=None,
                timestamp=datetime.now(tz=UTC),
            )
            attempts.append(attempt)
            return docker_result.stdout, attempts

        # Classify error
        error_class = classify_error(
            docker_result.stderr, docker_result.exit_code, docker_result.timed_out
        )

        attempt = AgentAttempt(
            attempt_number=attempt_num,
            generated_code=code,
            docker_result=docker_result,
            error_class=error_class,
            timestamp=datetime.now(tz=UTC),
        )
        attempts.append(attempt)

        # Check if retriable
        if not is_retriable(error_class):
            raise NonRetriableError(
                f"Non-retriable error ({error_class.value}): {docker_result.stderr[:500]}",
                error_class=error_class,
                attempts=attempts,
            )

        last_error = docker_result.stderr

    # All attempts exhausted
    raise MaxRetriesExceededError(
        f"Failed after {max_attempts} attempts",
        attempts=attempts,
    )
