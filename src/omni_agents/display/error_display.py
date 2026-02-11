"""Structured error display using Rich panels.

Renders pipeline errors as formatted Rich panels with agent context,
error classification, human-readable messages, and actionable fix suggestions.
Also handles consensus HALT verdicts with per-metric comparison tables.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from rich.panel import Panel
from rich.table import Table
from rich.text import Text

try:
    from rich.console import Group
except ImportError:
    Group = None  # type: ignore[assignment,misc]

from omni_agents.pipeline.retry import ERROR_SUGGESTIONS

if TYPE_CHECKING:
    from rich.console import Console

    from omni_agents.models.consensus import ConsensusVerdict


class ErrorDisplay:
    """Renders structured error panels for pipeline failures.

    All output goes through the shared ``Console`` instance (typically
    ``stderr=True``) so it does not interfere with stdout or the Rich Live
    display.
    """

    def __init__(self, console: Console) -> None:
        self.console = console

    def show_error(
        self,
        agent_name: str,
        error_class: str,
        message: str,
        suggestion: str,
    ) -> None:
        """Render a structured error panel.

        Args:
            agent_name: Name of the agent that produced the error.
            error_class: Classification of the error.
            message: Human-readable error description (truncated to 500 chars).
            suggestion: Actionable fix suggestion.
        """
        body = Text()
        body.append("Agent:       ", style="bold")
        body.append(f"{agent_name}\n")
        body.append("Error Class: ", style="bold")
        body.append(f"{error_class}\n")
        body.append("Message:     ", style="bold")
        body.append(f"{message[:500]}\n")
        body.append("Suggestion:  ", style="bold")
        body.append(suggestion)

        panel = Panel(
            body,
            border_style="red",
            title="Pipeline Error",
        )
        self.console.print(panel)

    def show_consensus_halt(self, verdict: ConsensusVerdict) -> None:
        """Render a consensus HALT panel with per-metric comparison table.

        Args:
            verdict: The ``ConsensusVerdict`` that triggered the HALT.
        """
        # Build per-metric comparison table.
        table = Table(title="Metric Comparisons", expand=True)
        table.add_column("Metric", style="bold")
        table.add_column("Track A", justify="right")
        table.add_column("Track B", justify="right")
        table.add_column("Tolerance")
        table.add_column("Within?", justify="center")

        for comp in verdict.comparisons:
            within_str = (
                "[green]yes[/green]"
                if comp.within_tolerance
                else "[red]no[/red]"
            )
            table.add_row(
                comp.metric,
                f"{comp.track_a_value:.4g}",
                f"{comp.track_b_value:.4g}",
                comp.tolerance_type,
                within_str,
            )

        # Build investigation hints.
        hints = Text()
        if verdict.investigation_hints:
            hints.append("\nInvestigation hints:\n", style="bold")
            for hint in verdict.investigation_hints:
                hints.append(f"  - {hint}\n")

        # Build boundary warnings.
        if verdict.boundary_warnings:
            hints.append("\nBoundary warnings:\n", style="bold")
            for warning in verdict.boundary_warnings:
                hints.append(f"  - {warning}\n")

        if Group is not None:
            content = Group(table, hints)
        else:
            # Fallback: use an outer Table as a vertical container.
            outer = Table(show_header=False, show_edge=False, pad_edge=False)
            outer.add_row(table)
            if hints.plain.strip():
                outer.add_row(hints)
            content = outer

        panel = Panel(
            content,
            border_style="red",
            title="Consensus HALT",
        )
        self.console.print(panel)

    @staticmethod
    def format_pipeline_error(
        error: Exception,
    ) -> tuple[str, str, str, str]:
        """Inspect an exception and return structured error fields.

        Returns:
            Tuple of ``(agent_name, error_class, message, suggestion)``.
        """
        from omni_agents.pipeline.consensus import ConsensusHaltError
        from omni_agents.pipeline.retry import (
            MaxRetriesExceededError,
            NonRetriableError,
        )

        if isinstance(error, NonRetriableError):
            return (
                error.agent_name,
                error.error_class.value,
                str(error),
                ERROR_SUGGESTIONS[error.error_class],
            )

        if isinstance(error, MaxRetriesExceededError):
            return (
                error.agent_name,
                "max_retries_exceeded",
                str(error),
                "Check logs for all attempt details",
            )

        if isinstance(error, ConsensusHaltError):
            return (
                "ConsensusJudge",
                "consensus_halt",
                str(error),
                "Review verdict.json for per-metric details",
            )

        return (
            "unknown",
            type(error).__name__,
            str(error)[:500],
            "Check pipeline logs for full stack trace",
        )
