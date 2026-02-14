"""Interactive pipeline display with stage-level pause points.

Extends PipelineDisplay with checkpoint support: stops the Rich Live
display, shows a summary panel, waits for user input via
run_in_executor (non-blocking to the event loop), then restarts
the Live display.
"""

import asyncio

from rich.panel import Panel
from rich.table import Table

from omni_agents.display.callbacks import InteractiveCallback
from omni_agents.display.pipeline_display import PipelineDisplay


def _read_input() -> str:
    """Read a line from stdin. Separated for testability."""
    return input()


class InteractivePipelineDisplay(PipelineDisplay):
    """Pipeline display with interactive pause points between stages.

    Implements InteractiveCallback by stopping Rich Live, rendering a
    summary panel, and waiting for Enter (via run_in_executor to avoid
    blocking the asyncio event loop).

    Non-TTY environments (CI, piped stdin) are detected via EOFError
    from input() -- pauses are silently skipped.
    """

    async def on_checkpoint(
        self,
        stage_name: str,
        summary: dict[str, str | list[str]],
    ) -> bool:
        """Pause pipeline and display stage summary.

        Stops Rich Live, prints a summary panel, waits for Enter.
        Returns True to continue, False to abort.

        Handles:
        - EOFError: stdin is not a TTY (CI) -- auto-continue
        - KeyboardInterrupt: Ctrl+C during pause -- abort
        """
        self.stop()

        # Build summary panel
        table = Table(show_header=False, show_edge=False, pad_edge=False, expand=True)
        table.add_column("Key", style="bold", ratio=1)
        table.add_column("Value", ratio=3)

        for key, value in summary.items():
            if isinstance(value, list):
                display_value = "\n".join(str(v) for v in value)
            else:
                display_value = str(value)
            table.add_row(key.replace("_", " ").title(), display_value)

        panel = Panel(
            table,
            title=f"[bold]Stage Complete: {stage_name}[/bold]",
            border_style="cyan",
            subtitle="[dim]Press Enter to continue, Ctrl+C to abort[/dim]",
        )
        self.console.print()
        self.console.print(panel)

        # Wait for user input via run_in_executor (INTER-05: non-blocking)
        try:
            loop = asyncio.get_running_loop()
            await loop.run_in_executor(None, _read_input)
        except EOFError:
            # Non-interactive terminal (CI, piped stdin) -- auto-continue
            # PITFALL-09: Interactive mode must not break CI
            self.console.print("[dim]Non-interactive terminal detected, continuing...[/dim]")
        except KeyboardInterrupt:
            # PITFALL-11: Graceful Ctrl+C during pause
            self.console.print("\n[yellow]Pipeline aborted by user at checkpoint.[/yellow]")
            return False

        self.start()
        return True
