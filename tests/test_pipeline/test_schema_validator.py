"""Tests for schema validator: ADaM sanity checks and output completeness.

Verifies:
- ADSL validation catches missing ADSL.csv, missing/wrong columns, wrong row count
- ADTTE with n_censored=0 raises SchemaValidationError
- ADTTE with event rate > 95% raises SchemaValidationError
- ADTTE with normal event rate passes validation
- Output completeness checks for data_dictionary.csv and ADSL.csv (DICT-05)
"""

import csv
import json
from pathlib import Path

import pytest

from omni_agents.models.schemas import REQUIRED_ADSL_COLS
from omni_agents.pipeline.schema_validator import (
    SchemaValidationError,
    SchemaValidator,
)

REQUIRED_COLS = [
    "STUDYID", "USUBJID", "PARAMCD", "PARAM",
    "AVAL", "CNSR", "STARTDT", "EVNTDESC",
    "AGE", "SEX", "ARM", "ARMCD",
]


def _make_adam_dir(
    tmp_path: Path,
    n_events: int,
    n_censored: int,
    *,
    include_adsl: bool = True,
) -> Path:
    """Create a minimal ADaM directory with ADTTE and optionally ADSL files."""
    adam_dir = tmp_path / "adam"
    adam_dir.mkdir()

    n_rows = n_events + n_censored

    # --- ADSL files (optional) ---
    if include_adsl:
        # Create ADSL.csv with all required columns and n_rows data rows
        adsl_cols = sorted(REQUIRED_ADSL_COLS)
        adsl_path = adam_dir / "ADSL.csv"
        with open(adsl_path, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=adsl_cols)
            writer.writeheader()
            for i in range(n_rows):
                row = {col: "" for col in adsl_cols}
                row["STUDYID"] = "SBP-001"
                row["USUBJID"] = f"SBP-001-SUBJ-{i:04d}"
                row["SUBJID"] = f"SUBJ-{i:04d}"
                row["AGE"] = "55"
                row["AGEU"] = "YEARS"
                row["AGEGR1"] = "<65"
                row["SEX"] = "M"
                row["RACE"] = "WHITE"
                row["ARM"] = "Treatment"
                row["ARMCD"] = "TRT"
                row["TRT01P"] = "Treatment"
                row["TRT01A"] = "Treatment"
                row["SAFFL"] = "Y"
                row["ITTFL"] = "Y"
                row["EFFFL"] = "Y"
                row["TRTSDT"] = "0"
                row["TRTEDT"] = "25"
                row["TRTDUR"] = "25"
                row["EOSSTT"] = "COMPLETED"
                row["DCSREAS"] = ""
                writer.writerow(row)

        # Create ADSL_summary.json
        adsl_summary = {
            "n_rows": n_rows,
            "columns": adsl_cols,
        }
        (adam_dir / "ADSL_summary.json").write_text(json.dumps(adsl_summary))

    # --- ADTTE files ---
    # Create a dummy ADTTE.rds (just needs to exist)
    (adam_dir / "ADTTE.rds").write_bytes(b"dummy")

    # Create ADTTE_summary.json
    adtte_summary = {
        "n_rows": n_rows,
        "n_events": n_events,
        "n_censored": n_censored,
        "columns": REQUIRED_COLS,
        "paramcd": "TTESB120",
    }
    (adam_dir / "ADTTE_summary.json").write_text(json.dumps(adtte_summary))

    return adam_dir


def test_adam_zero_censored_fails(tmp_path: Path) -> None:
    """n_censored=0 should fail — indicates Inf trap bug."""
    adam_dir = _make_adam_dir(tmp_path, n_events=300, n_censored=0)

    with pytest.raises(SchemaValidationError, match="n_censored is 0"):
        SchemaValidator.validate_adam(adam_dir, expected_subjects=300)


def test_adam_high_event_rate_fails(tmp_path: Path) -> None:
    """Event rate above 95% should fail — suspicious for this trial design."""
    adam_dir = _make_adam_dir(tmp_path, n_events=295, n_censored=5)

    with pytest.raises(SchemaValidationError, match="event rate is 98"):
        SchemaValidator.validate_adam(adam_dir, expected_subjects=300)


def test_adam_normal_event_rate_passes(tmp_path: Path) -> None:
    """Normal event rate (~72%) should pass validation."""
    adam_dir = _make_adam_dir(tmp_path, n_events=215, n_censored=85)

    # Should not raise
    SchemaValidator.validate_adam(adam_dir, expected_subjects=300)


# ---------------------------------------------------------------------------
# ADSL-specific validation tests
# ---------------------------------------------------------------------------


def test_adam_missing_adsl_csv_fails(tmp_path: Path) -> None:
    """validate_adam fails when ADSL.csv is missing."""
    adam_dir = _make_adam_dir(tmp_path, n_events=215, n_censored=85, include_adsl=False)
    with pytest.raises(SchemaValidationError, match="ADSL.csv not found"):
        SchemaValidator.validate_adam(adam_dir, expected_subjects=300)


def test_adam_missing_adsl_summary_fails(tmp_path: Path) -> None:
    """validate_adam fails when ADSL_summary.json is missing."""
    adam_dir = _make_adam_dir(tmp_path, n_events=215, n_censored=85)
    (adam_dir / "ADSL_summary.json").unlink()
    with pytest.raises(SchemaValidationError, match="ADSL_summary.json not found"):
        SchemaValidator.validate_adam(adam_dir, expected_subjects=300)


def test_adam_adsl_wrong_row_count_fails(tmp_path: Path) -> None:
    """validate_adam fails when ADSL has wrong number of rows."""
    adam_dir = _make_adam_dir(tmp_path, n_events=215, n_censored=85)
    # Overwrite summary with wrong row count
    summary = {"n_rows": 200, "columns": sorted(REQUIRED_ADSL_COLS)}
    (adam_dir / "ADSL_summary.json").write_text(json.dumps(summary))
    with pytest.raises(SchemaValidationError, match="ADSL.*expected 300.*got 200"):
        SchemaValidator.validate_adam(adam_dir, expected_subjects=300)


def test_adam_adsl_missing_columns_fails(tmp_path: Path) -> None:
    """validate_adam fails when ADSL is missing required columns."""
    adam_dir = _make_adam_dir(tmp_path, n_events=215, n_censored=85)
    # Overwrite summary with missing columns
    incomplete_cols = sorted(REQUIRED_ADSL_COLS - {"TRT01P", "SAFFL"})
    summary = {"n_rows": 300, "columns": incomplete_cols}
    (adam_dir / "ADSL_summary.json").write_text(json.dumps(summary))
    with pytest.raises(SchemaValidationError, match="ADSL.*missing required columns"):
        SchemaValidator.validate_adam(adam_dir, expected_subjects=300)


def test_adam_with_adsl_passes(tmp_path: Path) -> None:
    """validate_adam passes when both ADSL and ADTTE are valid."""
    adam_dir = _make_adam_dir(tmp_path, n_events=215, n_censored=85)
    # Should not raise
    SchemaValidator.validate_adam(adam_dir, expected_subjects=300)


# ---------------------------------------------------------------------------
# Output completeness tests (DICT-05)
# ---------------------------------------------------------------------------


def test_output_completeness_passes_with_dicts_and_adsl(tmp_path: Path) -> None:
    """Completeness check passes when data dictionaries and ADSL exist."""
    track_dir = tmp_path / "track"
    (track_dir / "sdtm").mkdir(parents=True)
    (track_dir / "adam").mkdir(parents=True)
    (track_dir / "sdtm" / "data_dictionary.csv").write_text("header\n")
    (track_dir / "adam" / "data_dictionary.csv").write_text("header\n")
    (track_dir / "adam" / "ADSL.csv").write_text("header\n")

    # Should not raise
    SchemaValidator.validate_output_completeness(track_dir)


def test_output_completeness_fails_missing_adsl(tmp_path: Path) -> None:
    """Completeness check fails when adam/ADSL.csv is missing."""
    track_dir = tmp_path / "track"
    (track_dir / "sdtm").mkdir(parents=True)
    (track_dir / "adam").mkdir(parents=True)
    (track_dir / "sdtm" / "data_dictionary.csv").write_text("header\n")
    (track_dir / "adam" / "data_dictionary.csv").write_text("header\n")
    # No ADSL.csv
    with pytest.raises(SchemaValidationError, match="ADSL.csv not found"):
        SchemaValidator.validate_output_completeness(track_dir)


def test_output_completeness_fails_missing_sdtm_dict(tmp_path: Path) -> None:
    """Completeness check fails when SDTM data dictionary is missing."""
    track_dir = tmp_path / "track"
    (track_dir / "sdtm").mkdir(parents=True)
    (track_dir / "adam").mkdir(parents=True)
    (track_dir / "adam" / "data_dictionary.csv").write_text("header\n")
    (track_dir / "adam" / "ADSL.csv").write_text("header\n")

    with pytest.raises(
        SchemaValidationError, match="sdtm/data_dictionary.csv not found"
    ):
        SchemaValidator.validate_output_completeness(track_dir)


def test_output_completeness_fails_missing_adam_dict(tmp_path: Path) -> None:
    """Completeness check fails when ADaM data dictionary is missing."""
    track_dir = tmp_path / "track"
    (track_dir / "sdtm").mkdir(parents=True)
    (track_dir / "adam").mkdir(parents=True)
    (track_dir / "sdtm" / "data_dictionary.csv").write_text("header\n")
    (track_dir / "adam" / "ADSL.csv").write_text("header\n")

    with pytest.raises(
        SchemaValidationError, match="adam/data_dictionary.csv not found"
    ):
        SchemaValidator.validate_output_completeness(track_dir)


def test_output_completeness_fails_missing_all(tmp_path: Path) -> None:
    """Completeness check fails with 3 issues when both dicts and ADSL missing."""
    track_dir = tmp_path / "track"
    (track_dir / "sdtm").mkdir(parents=True)
    (track_dir / "adam").mkdir(parents=True)

    with pytest.raises(SchemaValidationError) as exc_info:
        SchemaValidator.validate_output_completeness(track_dir)

    assert len(exc_info.value.issues) == 3
    assert exc_info.value.agent == "OutputCompleteness"
