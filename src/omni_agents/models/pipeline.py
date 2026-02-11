"""Pipeline state and step result models."""

from datetime import datetime
from enum import StrEnum
from pathlib import Path

from pydantic import BaseModel


class StepStatus(StrEnum):
    """Status of a pipeline step."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    RETRYING = "retrying"


class StepResult(BaseModel):
    """Result of a single execution attempt for a pipeline step."""

    success: bool
    output: str | None = None
    error: str | None = None
    code: str | None = None
    attempt: int
    duration_seconds: float


class StepState(BaseModel):
    """Current state of a pipeline step, including all attempts."""

    name: str
    agent_type: str
    track: str  # "shared", "track_a", "track_b"
    status: StepStatus = StepStatus.PENDING
    attempts: list[StepResult] = []
    max_attempts: int = 3


class PipelineState(BaseModel):
    """Complete state of a pipeline run, serializable for persistence and resume."""

    run_id: str
    started_at: datetime
    steps: dict[str, StepState] = {}
    current_step: str | None = None
    status: str = "running"  # "running", "completed", "failed"

    def save(self, path: Path) -> None:
        """Serialize pipeline state to a JSON file.

        Args:
            path: Destination file path.
        """
        path.write_text(self.model_dump_json(indent=2))

    @classmethod
    def load(cls, path: Path) -> "PipelineState":
        """Deserialize pipeline state from a JSON file.

        Args:
            path: Source file path.

        Returns:
            Loaded PipelineState instance.
        """
        return cls.model_validate_json(path.read_text())
