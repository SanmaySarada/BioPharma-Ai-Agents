"""Rich-based pipeline display with Live layout, status table, and progress bars.

``PipelineDisplay`` implements the ``ProgressCallback`` protocol, providing an
interactive terminal experience during pipeline execution.  In non-TTY
environments (CI, piped output) it falls back to plain text status lines.

All Rich output is routed through a shared ``Console(stderr=True)`` instance so
stdout remains clean for programmatic consumers.
"""

from __future__ import annotations

from rich.console import Console
from rich.panel import Panel
from rich.progress import (
    BarColumn,
    Progress,
    SpinnerColumn,
    TaskProgressColumn,
    TextColumn,
    TimeElapsedColumn,
)
from rich.table import Table
from rich.text import Text

try:
    from rich.console import Group
except ImportError:
    Group = None  # type: ignore[assignment,misc]

from omni_agents.display.callbacks import ProgressCallback

# Known pipeline steps in execution order.
_STEPS = [
    "simulator",
    "sdtm_track_a",
    "sdtm_track_b",
    "adam_track_a",
    "adam_track_b",
    "stats_track_a",
    "stats_track_b",
    "stage_comparison",
    "medical_writer",
]

# Steps that advance the Track A progress bar.
_TRACK_A_STEPS = {"sdtm_track_a", "adam_track_a", "stats_track_a"}

# Steps that advance the Track B progress bar.
_TRACK_B_STEPS = {"sdtm_track_b", "adam_track_b", "stats_track_b"}


class PipelineDisplay(ProgressCallback):
    """Interactive Rich display for pipeline progress.

    When running in a terminal, renders a Live layout with a status table
    (nine pipeline steps) and two progress bars (Track A, Track B).  In
    non-interactive environments, falls back to plain ``console.print`` calls.
    """

    def __init__(self) -> None:
        self.console = Console(stderr=True)
        self._interactive: bool = self.console.is_terminal

        # Step tracking state.
        self._steps: dict[str, dict] = {}
        for name in _STEPS:
            self._steps[name] = {
                "name": name,
                "status": "pending",
                "track": "",
                "attempts": 0,
                "duration": 0.0,
            }

        self._live = None
        self._progress: Progress | None = None
        self._track_a_task = None
        self._track_b_task = None

    # ------------------------------------------------------------------
    # Rich renderable builders
    # ------------------------------------------------------------------

    def _build_table(self) -> Table:
        """Build the status table showing all nine pipeline steps."""
        table = Table(title="Pipeline Steps", expand=True)
        table.add_column("Step", style="bold")
        table.add_column("Track")
        table.add_column("Status")
        table.add_column("Attempts", justify="right")
        table.add_column("Duration", justify="right")

        status_styles = {
            "done": "[green]done[/green]",
            "running": "[yellow]running[/yellow]",
            "failed": "[red]failed[/red]",
            "retrying": "[cyan]retrying[/cyan]",
            "pending": "[dim]pending[/dim]",
        }

        for name in _STEPS:
            step = self._steps[name]
            styled_status = status_styles.get(step["status"], step["status"])
            duration_str = (
                f'{step["duration"]:.1f}s' if step["duration"] > 0 else "-"
            )
            table.add_row(
                step["name"],
                step["track"],
                styled_status,
                str(step["attempts"]) if step["attempts"] > 0 else "-",
                duration_str,
            )

        return table

    def _build_progress(self) -> Progress:
        """Create the progress bar widget for Track A and Track B."""
        progress = Progress(
            SpinnerColumn(spinner_name="dots"),
            TextColumn("{task.description}"),
            BarColumn(),
            TaskProgressColumn(),
            TimeElapsedColumn(),
            console=self.console,
            disable=not self._interactive,
        )
        return progress

    def _build_renderable(self):
        """Compose the status table panel and progress bar into a single renderable."""
        panel = Panel(self._build_table(), border_style="blue", title="omni-agents")
        progress = self._progress

        if Group is not None:
            return Group(panel, progress)

        # Fallback: use a plain Table as a vertical container.
        outer = Table(show_header=False, show_edge=False, pad_edge=False)
        outer.add_row(panel)
        outer.add_row(progress)
        return outer

    # ------------------------------------------------------------------
    # Lifecycle methods
    # ------------------------------------------------------------------

    def start(self) -> None:
        """Start the Live display (interactive mode only).

        Safe to call multiple times -- Progress instances and task IDs are
        created only once. Subsequent calls restart only the Live context.
        """
        if self._progress is None:
            self._progress = self._build_progress()
            self._track_a_task = self._progress.add_task("Track A", total=3)
            self._track_b_task = self._progress.add_task("Track B", total=3)

        if self._interactive:
            from rich.live import Live

            renderable = self._build_renderable()
            self._live = Live(
                renderable, console=self.console, refresh_per_second=4
            )
            self._live.start()

    def stop(self) -> None:
        """Stop the Live display if active."""
        if self._live is not None:
            self._live.stop()
            self._live = None

    # ------------------------------------------------------------------
    # ProgressCallback implementation
    # ------------------------------------------------------------------

    def on_step_start(self, step_name: str, agent_type: str, track: str) -> None:
        if step_name in self._steps:
            self._steps[step_name]["status"] = "running"
            self._steps[step_name]["track"] = track
            self._steps[step_name]["attempts"] = 1
        self._refresh()

        if not self._interactive:
            self.console.print(f"[{step_name}] Starting ({agent_type}, {track})")

    def on_step_retry(
        self, step_name: str, attempt: int, max_attempts: int, error: str
    ) -> None:
        if step_name in self._steps:
            self._steps[step_name]["status"] = "retrying"
            self._steps[step_name]["attempts"] = attempt
        self._refresh()

        if not self._interactive:
            self.console.print(
                f"[{step_name}] Retrying ({attempt}/{max_attempts}): {error[:120]}"
            )

    def on_step_complete(
        self, step_name: str, duration_seconds: float, attempts: int
    ) -> None:
        if step_name in self._steps:
            self._steps[step_name]["status"] = "done"
            self._steps[step_name]["duration"] = duration_seconds
            self._steps[step_name]["attempts"] = attempts

        # Advance the appropriate progress bar.
        if self._progress is not None:
            if step_name in _TRACK_A_STEPS and self._track_a_task is not None:
                self._progress.advance(self._track_a_task, 1)
            elif step_name in _TRACK_B_STEPS and self._track_b_task is not None:
                self._progress.advance(self._track_b_task, 1)

        self._refresh()

        if not self._interactive:
            self.console.print(
                f"[{step_name}] Complete ({duration_seconds:.1f}s, {attempts} attempt(s))"
            )

    def on_step_fail(
        self, step_name: str, error_class: str, message: str, suggestion: str
    ) -> None:
        if step_name in self._steps:
            self._steps[step_name]["status"] = "failed"
        self._refresh()

    def on_llm_call(
        self,
        agent_name: str,
        model: str,
        input_tokens: int | None,
        output_tokens: int | None,
    ) -> None:
        if not self._interactive:
            self.console.print(
                f"[{agent_name}] LLM call: model={model} "
                f"in={input_tokens} out={output_tokens}"
            )

    def on_pipeline_complete(self, output_dir: str, total_seconds: float) -> None:
        self.stop()
        summary = Text.assemble(
            ("Pipeline completed in ", ""),
            (f"{total_seconds:.1f}s", "bold"),
            ("\nOutput: ", ""),
            (output_dir, "bold"),
        )
        panel = Panel(summary, border_style="green", title="Success")
        self.console.print(panel)

    def on_pipeline_fail(self, error: str) -> None:
        self.stop()

    def on_resolution_start(
        self, stage: str, iteration: int, max_iterations: int
    ) -> None:
        if not self._interactive:
            self.console.print(
                f"[resolution] Resolving {stage} disagreement "
                f"(iteration {iteration}/{max_iterations})"
            )

    def on_resolution_complete(
        self, stage: str, resolved: bool, iterations: int
    ) -> None:
        status = "resolved" if resolved else "unresolved"
        if not self._interactive:
            self.console.print(
                f"[resolution] {stage} {status} after {iterations} iteration(s)"
            )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _refresh(self) -> None:
        """Rebuild and update the Live renderable if in interactive mode."""
        if self._interactive and self._live is not None:
            self._live.update(self._build_renderable())
