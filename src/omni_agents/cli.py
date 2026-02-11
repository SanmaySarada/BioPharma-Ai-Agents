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
    from omni_agents.pipeline.orchestrator import PipelineOrchestrator

    settings = Settings.from_yaml(config)
    orchestrator = PipelineOrchestrator(settings)

    try:
        output_dir = asyncio.run(orchestrator.run())
        typer.echo(f"Pipeline completed successfully. Output: {output_dir}")
    except Exception as e:
        typer.echo(f"Pipeline failed: {e}", err=True)
        raise typer.Exit(code=1) from None
