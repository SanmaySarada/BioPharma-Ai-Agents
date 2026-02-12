"""Pipeline orchestration and DAG execution."""

from omni_agents.pipeline.logging import (
    log_agent_complete,
    log_agent_start,
    log_attempt,
    setup_logging,
)
from omni_agents.pipeline.orchestrator import PipelineOrchestrator
from omni_agents.pipeline.pre_execution import (
    PreExecutionError,
    check_r_code,
    validate_r_code,
)
from omni_agents.pipeline.retry import (
    MaxRetriesExceededError,
    NonRetriableError,
    classify_error,
    execute_with_retry,
    is_retriable,
)
from omni_agents.pipeline.stderr_filter import filter_r_stderr
from omni_agents.pipeline.schema_validator import (
    SchemaValidationError,
    SchemaValidator,
)

__all__ = [
    "MaxRetriesExceededError",
    "NonRetriableError",
    "PipelineOrchestrator",
    "PreExecutionError",
    "SchemaValidationError",
    "SchemaValidator",
    "check_r_code",
    "classify_error",
    "execute_with_retry",
    "filter_r_stderr",
    "is_retriable",
    "log_agent_complete",
    "log_agent_start",
    "log_attempt",
    "setup_logging",
    "validate_r_code",
]
