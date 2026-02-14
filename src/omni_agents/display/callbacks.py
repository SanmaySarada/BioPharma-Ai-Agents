"""Progress callback protocol for pipeline lifecycle events.

Defines the ``ProgressCallback`` Protocol that display implementations must
satisfy.  All lifecycle hooks are represented as methods with no return value,
allowing any concrete class (e.g. ``PipelineDisplay``) to be used wherever a
``ProgressCallback`` is expected.
"""

from typing import Protocol, runtime_checkable


@runtime_checkable
class ProgressCallback(Protocol):
    """Protocol for pipeline progress callbacks.

    Implementations receive lifecycle events during pipeline execution:
    step transitions, retries, LLM calls, and terminal states.
    """

    def on_step_start(self, step_name: str, agent_type: str, track: str) -> None:
        """Called when a pipeline step begins execution.

        Args:
            step_name: Identifier for the step. With symmetric tracks, step names
                are track-qualified: ``"sdtm_track_a"``, ``"adam_track_b"``, etc.
                Shared steps use unqualified names: ``"simulator"``, ``"consensus"``.
            agent_type: Class name of the agent (e.g. ``"SDTMAgent"``).
            track: Pipeline track (``"shared"``, ``"track_a"``, ``"track_b"``).
        """
        ...

    def on_step_retry(
        self, step_name: str, attempt: int, max_attempts: int, error: str
    ) -> None:
        """Called when a step is retried after a recoverable error.

        Args:
            step_name: Identifier for the step.
            attempt: Current attempt number (2+).
            max_attempts: Maximum attempts allowed.
            error: Error message from the previous attempt.
        """
        ...

    def on_step_complete(
        self, step_name: str, duration_seconds: float, attempts: int
    ) -> None:
        """Called when a step finishes successfully.

        Args:
            step_name: Identifier for the step.
            duration_seconds: Wall-clock time in seconds.
            attempts: Total attempts made (1 = first-try success).
        """
        ...

    def on_step_fail(
        self, step_name: str, error_class: str, message: str, suggestion: str
    ) -> None:
        """Called when a step fails permanently (non-retriable or max retries).

        Args:
            step_name: Identifier for the step.
            error_class: Classification of the error.
            message: Human-readable error message.
            suggestion: Actionable fix suggestion.
        """
        ...

    def on_llm_call(
        self,
        agent_name: str,
        model: str,
        input_tokens: int | None,
        output_tokens: int | None,
    ) -> None:
        """Called after each LLM API call completes.

        Args:
            agent_name: Name of the agent that made the call.
            model: Model identifier (e.g. ``"gemini-2.0-flash"``).
            input_tokens: Prompt token count, if available.
            output_tokens: Completion token count, if available.
        """
        ...

    def on_pipeline_complete(self, output_dir: str, total_seconds: float) -> None:
        """Called when the entire pipeline finishes successfully.

        Args:
            output_dir: Path to the run output directory.
            total_seconds: Total pipeline wall-clock time.
        """
        ...

    def on_pipeline_fail(self, error: str) -> None:
        """Called when the pipeline terminates with a fatal error.

        Args:
            error: Human-readable error description.
        """
        ...

    def on_resolution_start(
        self, stage: str, iteration: int, max_iterations: int
    ) -> None:
        """Called when resolution begins for a disagreeing stage.

        Args:
            stage: Pipeline stage being resolved ("sdtm", "adam", "stats").
            iteration: Current resolution iteration (1-indexed).
            max_iterations: Maximum iterations allowed.
        """
        ...

    def on_resolution_complete(
        self, stage: str, resolved: bool, iterations: int
    ) -> None:
        """Called when resolution finishes for a stage.

        Args:
            stage: Pipeline stage that was resolved.
            resolved: True if tracks now agree.
            iterations: Total resolution iterations performed.
        """
        ...


@runtime_checkable
class InteractiveCallback(ProgressCallback, Protocol):
    """Extended callback protocol for interactive execution mode.

    Adds checkpoint support to ProgressCallback. The orchestrator calls
    on_checkpoint() at stage boundaries when running in interactive mode.
    Non-interactive callbacks do not implement this and are unaffected.
    """

    async def on_checkpoint(
        self,
        stage_name: str,
        summary: dict[str, str | list[str]],
    ) -> bool:
        """Called at interactive pause points between pipeline stages.

        Args:
            stage_name: Human-readable name of the completed stage
                (e.g., "Simulator", "Parallel Analysis", "Stage Comparison").
            summary: Dict with keys like "status", "duration", "output_files",
                "metrics" -- contents vary per stage.

        Returns:
            True to continue pipeline execution, False to abort.
        """
        ...
