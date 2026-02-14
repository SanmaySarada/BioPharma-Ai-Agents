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
    interactive: bool = typer.Option(
        False,
        "--interactive",
        "-i",
        help="Pause between pipeline stages for step-by-step review",
    ),
) -> None:
    """Run the clinical trial pipeline."""
    from omni_agents.config import Settings
    from omni_agents.display.error_display import ErrorDisplay
    from omni_agents.display.pipeline_display import PipelineDisplay
    from omni_agents.pipeline.orchestrator import PipelineOrchestrator

    settings = Settings.from_yaml(config)

    # Create display infrastructure -- interactive mode uses extended display
    if interactive:
        from omni_agents.display.interactive_display import InteractivePipelineDisplay

        display = InteractivePipelineDisplay()
    else:
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


def _display_extraction(result: "ExtractionResult", console: "Console") -> None:
    """Display extracted protocol values in a Rich table.

    Shows each field's value and whether it was extracted from the
    document or fell back to the default.  Defaulted fields are
    highlighted in yellow as a warning (PITFALL-01, PITFALL-04).
    """
    from rich.table import Table

    table = Table(
        title="Protocol Extraction Results",
        show_header=True,
        header_style="bold",
    )
    table.add_column("Field", style="cyan")
    table.add_column("Value", style="white")
    table.add_column("Source", style="white")

    config_dict = result.config.model_dump()

    for field_name in sorted(config_dict.keys()):
        value = config_dict[field_name]
        if field_name in result.extracted_fields:
            source = "[green]extracted[/green]"
        else:
            source = "[yellow]DEFAULT[/yellow]"
        table.add_row(field_name, str(value), source)

    console.print()
    console.print(table)

    # Summary warning if many defaults
    n_defaults = len(result.defaulted_fields)
    n_total = len(config_dict)
    if n_defaults > 0:
        console.print(
            f"\n[yellow]Warning:[/yellow] {n_defaults}/{n_total} fields "
            f"used defaults (not found in protocol document)."
        )
        if n_defaults > n_total // 2:
            console.print(
                "[yellow]More than half the fields were not found. "
                "Review the protocol document for completeness.[/yellow]"
            )
    console.print()


def _write_config(trial_config: "TrialConfig", output_path: Path) -> None:
    """Write a TrialConfig as a YAML config file.

    Produces a ``config.yaml`` that ``Settings.from_yaml()`` can load.
    Only writes the trial section -- LLM and Docker config must be
    provided separately (via env vars or base config).
    """
    import yaml

    config_data = {
        "trial": trial_config.model_dump(),
        "llm": {
            "gemini": {
                "api_key": "$GEMINI_API_KEY",
                "model": "gemini-2.5-pro",
                "temperature": 0.0,
            },
            "openai": {
                "api_key": "$OPENAI_API_KEY",
                "model": "gpt-4o",
                "temperature": 0.0,
            },
        },
    }

    output_path.write_text(
        yaml.dump(config_data, default_flow_style=False, sort_keys=False)
    )


@app.command("parse-protocol")
def parse_protocol(
    protocol: Path = typer.Argument(
        ...,
        help="Path to .docx protocol document",
        exists=True,
    ),
    output: Path = typer.Option(
        "config.yaml",
        "--output",
        "-o",
        help="Output path for generated config YAML",
    ),
    config: Path = typer.Option(
        None,
        "--config",
        "-c",
        help="Base config YAML (for LLM settings). Uses env vars if not provided.",
    ),
    yes: bool = typer.Option(
        False,
        "--yes",
        "-y",
        help="Skip confirmation prompt and write config immediately",
    ),
) -> None:
    """Parse a clinical trial protocol document into pipeline config.

    Reads a .docx protocol document, extracts trial parameters using
    an LLM, and writes a config.yaml file compatible with the pipeline.

    Example:
        omni-agents parse-protocol protocol.docx -o config.yaml
    """
    import os

    from rich.console import Console
    from rich.prompt import Confirm

    # Resolve LLM adapter
    if config is not None:
        from omni_agents.config import Settings

        settings = Settings.from_yaml(config)
        gemini_config = settings.llm.gemini
    else:
        from omni_agents.config import GeminiConfig

        api_key = os.environ.get("GEMINI_API_KEY")
        if not api_key:
            console = Console()
            console.print(
                "[red]Error:[/red] GEMINI_API_KEY not set. "
                "Provide --config or set the environment variable."
            )
            raise typer.Exit(code=1)
        gemini_config = GeminiConfig(api_key=api_key)

    from omni_agents.agents.protocol_parser import ProtocolParserAgent
    from omni_agents.llm.gemini import GeminiAdapter

    llm = GeminiAdapter(gemini_config)
    prompt_dir = Path(__file__).parent / "templates" / "prompts"
    agent = ProtocolParserAgent(llm=llm, prompt_dir=prompt_dir)

    console = Console()
    try:
        result = asyncio.run(agent.parse(protocol))
    except Exception as e:
        console.print(f"[red]Error parsing protocol:[/red] {e}")
        raise typer.Exit(code=1) from None

    _display_extraction(result, console)

    if not yes:
        if not Confirm.ask("Write this config?", default=True, console=console):
            console.print("[yellow]Aborted.[/yellow] Config not written.")
            raise typer.Exit(code=0)

    _write_config(result.config, output)
    console.print(f"[green]Config written to {output}[/green]")
    console.print(f"Run: [bold]omni-agents run -c {output}[/bold]")


if __name__ == "__main__":
    app()
