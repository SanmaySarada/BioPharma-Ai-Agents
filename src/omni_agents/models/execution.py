"""Docker execution and retry state models."""

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel


class ErrorClassification(StrEnum):
    """Classification of R execution errors for retry strategy."""

    CODE_BUG = "code_bug"
    ENVIRONMENT_ERROR = "environment_error"
    DATA_PATH_ERROR = "data_path_error"
    STATISTICAL_ERROR = "statistical_error"
    TIMEOUT = "timeout"
    UNKNOWN = "unknown"


class DockerResult(BaseModel):
    """Result of executing R code in a Docker container."""

    exit_code: int
    stdout: str
    stderr: str
    duration_seconds: float
    timed_out: bool = False


class RetryState(BaseModel):
    """State tracking for the error-feedback retry loop."""

    attempt: int
    max_attempts: int
    last_error: str | None = None
    error_class: ErrorClassification | None = None
    generated_code: str | None = None


class AgentAttempt(BaseModel):
    """Record of a single agent execution attempt for audit trail."""

    attempt_number: int
    generated_code: str
    docker_result: DockerResult | None = None
    error_class: ErrorClassification | None = None
    timestamp: datetime
