"""Tests for the Protocol Parser Agent and CLI integration."""

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import yaml
from typer.testing import CliRunner

from omni_agents.agents.protocol_parser import ProtocolParserAgent
from omni_agents.cli import _display_extraction, _write_config, app
from omni_agents.config import (
    ExtractionResult,
    ProtocolExtraction,
    TrialConfig,
    merge_extraction,
)

runner = CliRunner()


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_llm():
    """Create a mock LLM that returns a partial ProtocolExtraction."""
    llm = MagicMock()
    llm.generate_structured = AsyncMock(
        return_value=ProtocolExtraction(
            n_subjects=500,
            treatment_sbp_mean=115.0,
            dropout_rate=0.15,
        )
    )
    return llm


@pytest.fixture
def prompt_dir():
    """Return the path to the real prompt templates directory."""
    return Path(__file__).parents[2] / "src" / "omni_agents" / "templates" / "prompts"


@pytest.fixture
def sample_result():
    """Create a sample ExtractionResult for display/write tests."""
    extraction = ProtocolExtraction(
        n_subjects=500,
        treatment_sbp_mean=115.0,
        dropout_rate=0.15,
    )
    return merge_extraction(extraction)


# ---------------------------------------------------------------------------
# ProtocolParserAgent
# ---------------------------------------------------------------------------


class TestProtocolParserAgent:
    """Unit tests for ProtocolParserAgent."""

    def test_parse_calls_extract_protocol_text(
        self, mock_llm, prompt_dir
    ) -> None:
        agent = ProtocolParserAgent(llm=mock_llm, prompt_dir=prompt_dir)
        with patch(
            "omni_agents.agents.protocol_parser.extract_protocol_text"
        ) as mock_extract:
            mock_extract.return_value = "Protocol text with 500 subjects"
            asyncio.run(agent.parse(Path("fake.docx")))
            mock_extract.assert_called_once_with(Path("fake.docx"))

    def test_parse_calls_generate_structured(
        self, mock_llm, prompt_dir
    ) -> None:
        agent = ProtocolParserAgent(llm=mock_llm, prompt_dir=prompt_dir)
        with patch(
            "omni_agents.agents.protocol_parser.extract_protocol_text"
        ) as mock_extract:
            mock_extract.return_value = "Protocol text"
            asyncio.run(agent.parse(Path("fake.docx")))
            mock_llm.generate_structured.assert_called_once()
            call_kwargs = mock_llm.generate_structured.call_args
            assert call_kwargs.kwargs["response_model"] is ProtocolExtraction

    def test_parse_returns_extraction_result(
        self, mock_llm, prompt_dir
    ) -> None:
        agent = ProtocolParserAgent(llm=mock_llm, prompt_dir=prompt_dir)
        with patch(
            "omni_agents.agents.protocol_parser.extract_protocol_text"
        ) as mock_extract:
            mock_extract.return_value = "Protocol text"
            result = asyncio.run(agent.parse(Path("fake.docx")))
            assert isinstance(result, ExtractionResult)
            assert "n_subjects" in result.extracted_fields
            assert "treatment_sbp_mean" in result.extracted_fields
            assert "dropout_rate" in result.extracted_fields
            assert "visits" in result.defaulted_fields
            assert result.config.n_subjects == 500

    def test_parse_with_custom_defaults(
        self, mock_llm, prompt_dir
    ) -> None:
        custom = TrialConfig(visits=52, endpoint="DBP")
        agent = ProtocolParserAgent(llm=mock_llm, prompt_dir=prompt_dir)
        with patch(
            "omni_agents.agents.protocol_parser.extract_protocol_text"
        ) as mock_extract:
            mock_extract.return_value = "Protocol text"
            result = asyncio.run(agent.parse(Path("fake.docx"), defaults=custom))
            # Extracted fields override
            assert result.config.n_subjects == 500
            # Non-extracted fields use custom defaults
            assert result.config.visits == 52
            assert result.config.endpoint == "DBP"

    def test_parse_file_not_found(self, mock_llm, prompt_dir) -> None:
        agent = ProtocolParserAgent(llm=mock_llm, prompt_dir=prompt_dir)
        with pytest.raises(FileNotFoundError):
            asyncio.run(agent.parse(Path("/nonexistent/protocol.docx")))


# ---------------------------------------------------------------------------
# _display_extraction
# ---------------------------------------------------------------------------


class TestDisplayExtraction:
    """Tests for the Rich extraction display helper."""

    def test_display_shows_all_fields(self, sample_result) -> None:
        console = MagicMock()
        _display_extraction(sample_result, console)
        # Console.print is called multiple times: empty line, table, summary, etc.
        assert console.print.call_count >= 2

    def test_display_flags_defaults_yellow(self, sample_result) -> None:
        """Verify defaulted fields are marked with DEFAULT."""
        console = MagicMock()
        _display_extraction(sample_result, console)
        # The table is the second print call (after the blank line)
        # Check that the warning about defaults is printed
        all_calls = [str(c) for c in console.print.call_args_list]
        combined = " ".join(all_calls)
        assert "DEFAULT" in combined or "defaults" in combined.lower()

    def test_display_shows_extracted_green(self, sample_result) -> None:
        """Verify extracted fields are rendered in the table."""
        from io import StringIO

        from rich.console import Console as RealConsole

        buf = StringIO()
        console = RealConsole(file=buf, force_terminal=True, width=120)
        _display_extraction(sample_result, console)
        output = buf.getvalue()
        assert "extracted" in output.lower()

    def test_display_warns_on_many_defaults(self) -> None:
        """When >50% defaulted, show extra warning."""
        # Only extract 2 fields -- most will be defaulted
        extraction = ProtocolExtraction(n_subjects=500, endpoint="SBP")
        result = merge_extraction(extraction)
        console = MagicMock()
        _display_extraction(result, console)
        all_calls = [str(c) for c in console.print.call_args_list]
        combined = " ".join(all_calls)
        assert "More than half" in combined


# ---------------------------------------------------------------------------
# _write_config
# ---------------------------------------------------------------------------


class TestWriteConfig:
    """Tests for the YAML config writer."""

    def test_write_config_creates_valid_yaml(
        self, tmp_path, sample_result
    ) -> None:
        output = tmp_path / "config.yaml"
        _write_config(sample_result.config, output)
        assert output.exists()
        data = yaml.safe_load(output.read_text())
        assert isinstance(data, dict)

    def test_write_config_has_trial_section(
        self, tmp_path, sample_result
    ) -> None:
        output = tmp_path / "config.yaml"
        _write_config(sample_result.config, output)
        data = yaml.safe_load(output.read_text())
        assert "trial" in data
        trial = data["trial"]
        assert trial["n_subjects"] == 500
        assert trial["treatment_sbp_mean"] == 115.0

    def test_write_config_has_env_var_placeholders(
        self, tmp_path, sample_result
    ) -> None:
        output = tmp_path / "config.yaml"
        _write_config(sample_result.config, output)
        data = yaml.safe_load(output.read_text())
        assert data["llm"]["gemini"]["api_key"] == "$GEMINI_API_KEY"
        assert data["llm"]["openai"]["api_key"] == "$OPENAI_API_KEY"

    def test_written_config_roundtrips(
        self, tmp_path, sample_result, monkeypatch
    ) -> None:
        """Write config, set env vars, load with Settings.from_yaml()."""
        from omni_agents.config import Settings

        output = tmp_path / "config.yaml"
        _write_config(sample_result.config, output)

        monkeypatch.setenv("GEMINI_API_KEY", "test-gemini-key")
        monkeypatch.setenv("OPENAI_API_KEY", "test-openai-key")

        settings = Settings.from_yaml(output)
        assert settings.trial.n_subjects == 500
        assert settings.trial.treatment_sbp_mean == 115.0
        assert settings.trial.dropout_rate == 0.15


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


class TestParseProtocolCLI:
    """Tests for the parse-protocol CLI subcommand."""

    def test_help_output(self) -> None:
        result = runner.invoke(app, ["parse-protocol", "--help"])
        assert result.exit_code == 0
        assert "protocol" in result.output.lower()
        assert "--output" in result.output
        assert "--yes" in result.output

    def test_missing_protocol_arg(self) -> None:
        result = runner.invoke(app, ["parse-protocol"])
        assert result.exit_code != 0
