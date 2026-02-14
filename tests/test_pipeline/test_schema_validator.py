"""Tests for ADaM validation sanity checks (Inf trap detection).

Verifies:
- ADTTE with n_censored=0 raises SchemaValidationError
- ADTTE with event rate > 95% raises SchemaValidationError
- ADTTE with normal event rate passes validation
"""

import json
from pathlib import Path

import pytest

from omni_agents.pipeline.schema_validator import (
    SchemaValidationError,
    SchemaValidator,
)

REQUIRED_COLS = [
    "STUDYID", "USUBJID", "PARAMCD", "PARAM",
    "AVAL", "CNSR", "STARTDT", "EVNTDESC",
    "AGE", "SEX", "ARM", "ARMCD",
]


def _make_adam_dir(tmp_path: Path, n_events: int, n_censored: int) -> Path:
    """Create a minimal ADaM directory with ADTTE.rds and ADTTE_summary.json."""
    adam_dir = tmp_path / "adam"
    adam_dir.mkdir()

    # Create a dummy ADTTE.rds (just needs to exist)
    (adam_dir / "ADTTE.rds").write_bytes(b"dummy")

    # Create ADTTE_summary.json
    n_rows = n_events + n_censored
    summary = {
        "n_rows": n_rows,
        "n_events": n_events,
        "n_censored": n_censored,
        "columns": REQUIRED_COLS,
        "paramcd": "TTESB120",
    }
    (adam_dir / "ADTTE_summary.json").write_text(json.dumps(summary))

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
