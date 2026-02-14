"""Tests for ProtocolExtraction model and merge logic."""

import pytest

from omni_agents.config import (
    ExtractionResult,
    ProtocolExtraction,
    TrialConfig,
    merge_extraction,
)


# ---------------------------------------------------------------------------
# ProtocolExtraction model
# ---------------------------------------------------------------------------


class TestProtocolExtraction:
    """Unit tests for the ProtocolExtraction Pydantic model."""

    def test_all_none_by_default(self) -> None:
        extraction = ProtocolExtraction()
        for field_name in ProtocolExtraction.model_fields:
            assert getattr(extraction, field_name) is None

    def test_partial_extraction(self) -> None:
        extraction = ProtocolExtraction(n_subjects=500, endpoint="SBP")
        assert extraction.n_subjects == 500
        assert extraction.endpoint == "SBP"
        assert extraction.visits is None
        assert extraction.dropout_rate is None

    def test_field_parity_with_trial_config(self) -> None:
        """All TrialConfig field names must exist in ProtocolExtraction."""
        trial_fields = set(TrialConfig.model_fields.keys())
        extraction_fields = set(ProtocolExtraction.model_fields.keys())
        assert trial_fields == extraction_fields


# ---------------------------------------------------------------------------
# merge_extraction
# ---------------------------------------------------------------------------


class TestMergeExtraction:
    """Unit tests for the merge_extraction function."""

    def test_full_extraction_no_defaults(self) -> None:
        extraction = ProtocolExtraction(
            n_subjects=500,
            randomization_ratio="1:1",
            seed=99999,
            visits=12,
            endpoint="DBP",
            treatment_sbp_mean=115.0,
            treatment_sbp_sd=8.0,
            placebo_sbp_mean=135.0,
            placebo_sbp_sd=18.0,
            baseline_sbp_mean=148.0,
            baseline_sbp_sd=9.0,
            age_mean=60.0,
            age_sd=12.0,
            missing_rate=0.05,
            dropout_rate=0.12,
        )
        result = merge_extraction(extraction)
        assert len(result.defaulted_fields) == 0
        assert len(result.extracted_fields) == len(TrialConfig.model_fields)

    def test_empty_extraction_all_defaults(self) -> None:
        extraction = ProtocolExtraction()
        result = merge_extraction(extraction)
        assert len(result.extracted_fields) == 0
        assert set(result.defaulted_fields) == set(TrialConfig.model_fields.keys())
        # Config should equal default TrialConfig
        assert result.config == TrialConfig()

    def test_partial_extraction_mixed(self) -> None:
        extraction = ProtocolExtraction(
            n_subjects=500,
            treatment_sbp_mean=115.0,
            dropout_rate=0.15,
        )
        result = merge_extraction(extraction)
        assert "n_subjects" in result.extracted_fields
        assert "treatment_sbp_mean" in result.extracted_fields
        assert "dropout_rate" in result.extracted_fields
        assert "visits" in result.defaulted_fields
        assert "endpoint" in result.defaulted_fields

    def test_extracted_values_override_defaults(self) -> None:
        extraction = ProtocolExtraction(n_subjects=500)
        result = merge_extraction(extraction)
        assert result.config.n_subjects == 500
        # Default is 300
        assert TrialConfig().n_subjects == 300

    def test_default_values_preserved(self) -> None:
        extraction = ProtocolExtraction(n_subjects=500)
        result = merge_extraction(extraction)
        default = TrialConfig()
        # Non-extracted fields should use defaults
        assert result.config.visits == default.visits
        assert result.config.endpoint == default.endpoint
        assert result.config.missing_rate == default.missing_rate

    def test_seed_treated_normally(self) -> None:
        """Seed is a normal field -- if LLM extracts it, it is used."""
        extraction = ProtocolExtraction(seed=42)
        result = merge_extraction(extraction)
        assert result.config.seed == 42
        assert "seed" in result.extracted_fields

    def test_custom_defaults(self) -> None:
        custom = TrialConfig(n_subjects=1000, visits=52, endpoint="DBP")
        extraction = ProtocolExtraction(n_subjects=500)
        result = merge_extraction(extraction, defaults=custom)
        # Extracted field overrides
        assert result.config.n_subjects == 500
        # Non-extracted fields use custom defaults
        assert result.config.visits == 52
        assert result.config.endpoint == "DBP"

    def test_extraction_result_fields_complete(self) -> None:
        extraction = ProtocolExtraction(n_subjects=500, endpoint="SBP")
        result = merge_extraction(extraction)
        all_fields = set(result.extracted_fields) | set(result.defaulted_fields)
        assert all_fields == set(TrialConfig.model_fields.keys())
