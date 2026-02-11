"""Typer CLI entry point for omni-agents pipeline."""

import asyncio
from pathlib import Path

import typer
from dotenv import load_dotenv

load_dotenv()

app = typer.Typer(
    name="omni-agents",
    help="Multi-LLM clinical trial orchestration CLI",
    no_args_is_help=True,
)


_config_option = typer.Option(
    "config.yaml",
    "--config",
    "-c",
    help="Path to configuration YAML file",
    exists=True,
)


@app.command()
def run(
    config: Path = _config_option,
) -> None:
    """Run the clinical trial pipeline."""
    from omni_agents.config import Settings
    from omni_agents.display.error_display import ErrorDisplay
    from omni_agents.display.pipeline_display import PipelineDisplay
    from omni_agents.pipeline.orchestrator import PipelineOrchestrator

    settings = Settings.from_yaml(config)

    # Create display infrastructure
    display = PipelineDisplay()
    error_display = ErrorDisplay(display.console)

    # Pass display as callback AND display.console for logging routing.
    # The orchestrator will forward display.console to setup_logging()
    # so that loguru output goes through the shared Rich Console
    # instead of writing directly to stderr (which would corrupt
    # the Rich Live display).
    orchestrator = PipelineOrchestrator(
        settings, callback=display, console=display.console
    )

    try:
        display.start()
        asyncio.run(orchestrator.run())
        display.stop()
        # Final success message is handled by on_pipeline_complete callback
    except KeyboardInterrupt:
        display.stop()
        error_display.show_error(
            "pipeline",
            "interrupted",
            "Pipeline interrupted by user",
            "Re-run with the same config to resume",
        )
        raise typer.Exit(code=130) from None
    except Exception as e:
        display.stop()
        agent_name, error_class, message, suggestion = (
            ErrorDisplay.format_pipeline_error(e)
        )
        error_display.show_error(agent_name, error_class, message, suggestion)
        raise typer.Exit(code=1) from None
