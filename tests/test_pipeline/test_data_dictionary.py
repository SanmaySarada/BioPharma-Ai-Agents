"""Tests for per-dataset data dictionary generation (DICT-02, DICT-03, DICT-04)."""

import csv
from pathlib import Path

from omni_agents.config import TrialConfig
from omni_agents.pipeline.data_dictionary import (
    write_adsl_data_dictionary,
    write_adtte_data_dictionary,
    write_dm_data_dictionary,
    write_vs_data_dictionary,
)


# ---------------------------------------------------------------------------
# DM data dictionary
# ---------------------------------------------------------------------------


def test_dm_data_dictionary_creates_file(tmp_path: Path) -> None:
    """DM data dictionary file is created in the given directory."""
    write_dm_data_dictionary(tmp_path, TrialConfig())
    assert (tmp_path / "DM_data_dictionary.csv").exists()


def test_dm_data_dictionary_has_correct_columns(tmp_path: Path) -> None:
    """DM data dictionary CSV has exactly the four required columns."""
    write_dm_data_dictionary(tmp_path, TrialConfig())
    with open(tmp_path / "DM_data_dictionary.csv") as f:
        reader = csv.DictReader(f)
        list(reader)
        assert reader.fieldnames == ["Variable", "Label", "Type", "Derivation"]


def test_dm_data_dictionary_contains_dm_variables(tmp_path: Path) -> None:
    """DM data dictionary contains expected DM domain variables."""
    write_dm_data_dictionary(tmp_path, TrialConfig())
    with open(tmp_path / "DM_data_dictionary.csv") as f:
        reader = csv.DictReader(f)
        rows = list(reader)
    variables = [row["Variable"] for row in rows]
    for var in ("STUDYID", "USUBJID", "AGE", "SEX", "RACE", "ARM", "ACTARM"):
        assert var in variables, f"Missing DM variable: {var}"


def test_dm_data_dictionary_returns_path(tmp_path: Path) -> None:
    """write_dm_data_dictionary returns the Path to the written CSV."""
    result = write_dm_data_dictionary(tmp_path, TrialConfig())
    assert result == tmp_path / "DM_data_dictionary.csv"


def test_dm_data_dictionary_does_not_contain_vs_variables(tmp_path: Path) -> None:
    """DM data dictionary should NOT contain VS-specific variables."""
    write_dm_data_dictionary(tmp_path, TrialConfig())
    with open(tmp_path / "DM_data_dictionary.csv") as f:
        reader = csv.DictReader(f)
        rows = list(reader)
    variables = [row["Variable"] for row in rows]
    for var in ("VSTESTCD", "VSTEST", "VSSTRESN", "VSBLFL"):
        assert var not in variables, f"VS variable {var} should not be in DM dict"


# ---------------------------------------------------------------------------
# VS data dictionary
# ---------------------------------------------------------------------------


def test_vs_data_dictionary_creates_file(tmp_path: Path) -> None:
    """VS data dictionary file is created in the given directory."""
    write_vs_data_dictionary(tmp_path, TrialConfig())
    assert (tmp_path / "VS_data_dictionary.csv").exists()


def test_vs_data_dictionary_has_correct_columns(tmp_path: Path) -> None:
    """VS data dictionary CSV has exactly the four required columns."""
    write_vs_data_dictionary(tmp_path, TrialConfig())
    with open(tmp_path / "VS_data_dictionary.csv") as f:
        reader = csv.DictReader(f)
        list(reader)
        assert reader.fieldnames == ["Variable", "Label", "Type", "Derivation"]


def test_vs_data_dictionary_contains_vs_variables(tmp_path: Path) -> None:
    """VS data dictionary contains expected VS domain variables."""
    write_vs_data_dictionary(tmp_path, TrialConfig())
    with open(tmp_path / "VS_data_dictionary.csv") as f:
        reader = csv.DictReader(f)
        rows = list(reader)
    variables = [row["Variable"] for row in rows]
    for var in ("VSTESTCD", "VSTEST", "VSSTRESN", "VISITNUM", "VSBLFL"):
        assert var in variables, f"Missing VS variable: {var}"


def test_vs_data_dictionary_returns_path(tmp_path: Path) -> None:
    """write_vs_data_dictionary returns the Path to the written CSV."""
    result = write_vs_data_dictionary(tmp_path, TrialConfig())
    assert result == tmp_path / "VS_data_dictionary.csv"


def test_vs_data_dictionary_does_not_contain_dm_variables(tmp_path: Path) -> None:
    """VS data dictionary should NOT contain DM-only variables like ARM."""
    write_vs_data_dictionary(tmp_path, TrialConfig())
    with open(tmp_path / "VS_data_dictionary.csv") as f:
        reader = csv.DictReader(f)
        rows = list(reader)
    variables = [row["Variable"] for row in rows]
    for var in ("ARM", "ARMCD", "ACTARM", "ACTARMCD", "AGE", "RACE"):
        assert var not in variables, f"DM variable {var} should not be in VS dict"


# ---------------------------------------------------------------------------
# ADSL data dictionary
# ---------------------------------------------------------------------------


def test_adsl_data_dictionary_creates_file(tmp_path: Path) -> None:
    """ADSL data dictionary file is created in the given directory."""
    write_adsl_data_dictionary(tmp_path, TrialConfig())
    assert (tmp_path / "ADSL_data_dictionary.csv").exists()


def test_adsl_data_dictionary_has_correct_columns(tmp_path: Path) -> None:
    """ADSL data dictionary CSV has exactly the four required columns."""
    write_adsl_data_dictionary(tmp_path, TrialConfig())
    with open(tmp_path / "ADSL_data_dictionary.csv") as f:
        reader = csv.DictReader(f)
        list(reader)
        assert reader.fieldnames == ["Variable", "Label", "Type", "Derivation"]


def test_adsl_data_dictionary_contains_adsl_variables(tmp_path: Path) -> None:
    """ADSL data dictionary contains population flags and treatment vars."""
    write_adsl_data_dictionary(tmp_path, TrialConfig())
    with open(tmp_path / "ADSL_data_dictionary.csv") as f:
        reader = csv.DictReader(f)
        rows = list(reader)
    variables = [row["Variable"] for row in rows]
    for var in (
        "TRT01P", "TRT01A", "SAFFL", "ITTFL", "EFFFL",
        "TRTSDT", "TRTEDT", "TRTDUR", "EOSSTT", "DCSREAS",
        "AGEGR1", "AGEU",
    ):
        assert var in variables, f"Missing ADSL variable: {var}"


def test_adsl_data_dictionary_returns_path(tmp_path: Path) -> None:
    """write_adsl_data_dictionary returns the Path to the written CSV."""
    result = write_adsl_data_dictionary(tmp_path, TrialConfig())
    assert result == tmp_path / "ADSL_data_dictionary.csv"


def test_adsl_data_dictionary_does_not_contain_adtte_variables(tmp_path: Path) -> None:
    """ADSL data dictionary should NOT contain ADTTE-specific variables."""
    write_adsl_data_dictionary(tmp_path, TrialConfig())
    with open(tmp_path / "ADSL_data_dictionary.csv") as f:
        reader = csv.DictReader(f)
        rows = list(reader)
    variables = [row["Variable"] for row in rows]
    for var in ("PARAMCD", "PARAM", "AVAL", "CNSR", "EVNTDESC"):
        assert var not in variables, f"ADTTE variable {var} should not be in ADSL dict"


# ---------------------------------------------------------------------------
# ADTTE data dictionary
# ---------------------------------------------------------------------------


def test_adtte_data_dictionary_creates_file(tmp_path: Path) -> None:
    """ADTTE data dictionary file is created in the given directory."""
    write_adtte_data_dictionary(tmp_path, TrialConfig())
    assert (tmp_path / "ADTTE_data_dictionary.csv").exists()


def test_adtte_data_dictionary_has_correct_columns(tmp_path: Path) -> None:
    """ADTTE data dictionary CSV has exactly the four required columns."""
    write_adtte_data_dictionary(tmp_path, TrialConfig())
    with open(tmp_path / "ADTTE_data_dictionary.csv") as f:
        reader = csv.DictReader(f)
        list(reader)
        assert reader.fieldnames == ["Variable", "Label", "Type", "Derivation"]


def test_adtte_data_dictionary_contains_adtte_variables(tmp_path: Path) -> None:
    """ADTTE data dictionary contains all expected ADTTE variables."""
    write_adtte_data_dictionary(tmp_path, TrialConfig())
    with open(tmp_path / "ADTTE_data_dictionary.csv") as f:
        reader = csv.DictReader(f)
        rows = list(reader)
    variables = [row["Variable"] for row in rows]
    for var in (
        "USUBJID", "PARAMCD", "PARAM", "AVAL", "CNSR",
        "STARTDT", "EVNTDESC", "AGE", "SEX", "ARM",
    ):
        assert var in variables, f"Missing ADTTE variable: {var}"


def test_adtte_data_dictionary_uses_event_threshold(tmp_path: Path) -> None:
    """ADTTE data dictionary derivation text is parameterized by event_threshold."""
    tc = TrialConfig(treatment_sbp_mean=130.0)
    write_adtte_data_dictionary(tmp_path, tc)
    with open(tmp_path / "ADTTE_data_dictionary.csv") as f:
        reader = csv.DictReader(f)
        rows = list(reader)
    derivations = [row["Derivation"] for row in rows]
    assert any(
        "130" in d for d in derivations
    ), "Expected event_threshold (130) in at least one derivation"


def test_adtte_data_dictionary_returns_path(tmp_path: Path) -> None:
    """write_adtte_data_dictionary returns the Path to the written CSV."""
    result = write_adtte_data_dictionary(tmp_path, TrialConfig())
    assert result == tmp_path / "ADTTE_data_dictionary.csv"


def test_adtte_data_dictionary_references_adsl(tmp_path: Path) -> None:
    """ADTTE AGE/SEX/ARM/ARMCD derivations reference ADSL, not DM directly."""
    write_adtte_data_dictionary(tmp_path, TrialConfig())
    with open(tmp_path / "ADTTE_data_dictionary.csv") as f:
        reader = csv.DictReader(f)
        rows = list(reader)
    for row in rows:
        if row["Variable"] in ("AGE", "SEX", "ARM", "ARMCD"):
            assert "ADSL" in row["Derivation"], (
                f"ADTTE {row['Variable']} derivation should reference ADSL, "
                f"got: {row['Derivation']}"
            )


# ---------------------------------------------------------------------------
# Cross-cutting tests
# ---------------------------------------------------------------------------


def test_data_dictionary_is_deterministic(tmp_path: Path) -> None:
    """Writing the same dictionary twice produces identical output (DICT-04)."""
    dir_a = tmp_path / "a"
    dir_a.mkdir()
    dir_b = tmp_path / "b"
    dir_b.mkdir()

    tc = TrialConfig()
    write_dm_data_dictionary(dir_a, tc)
    write_dm_data_dictionary(dir_b, tc)

    content_a = (dir_a / "DM_data_dictionary.csv").read_text()
    content_b = (dir_b / "DM_data_dictionary.csv").read_text()
    assert content_a == content_b


def test_adtte_data_dictionary_derivation_text_not_empty(tmp_path: Path) -> None:
    """Every ADTTE data dictionary row has a non-empty Derivation field."""
    write_adtte_data_dictionary(tmp_path, TrialConfig())
    with open(tmp_path / "ADTTE_data_dictionary.csv") as f:
        reader = csv.DictReader(f)
        rows = list(reader)
    for row in rows:
        assert row["Derivation"].strip(), (
            f"Empty Derivation for variable {row['Variable']}"
        )


def test_adsl_data_dictionary_derivation_text_not_empty(tmp_path: Path) -> None:
    """Every ADSL data dictionary row has a non-empty Derivation field."""
    write_adsl_data_dictionary(tmp_path, TrialConfig())
    with open(tmp_path / "ADSL_data_dictionary.csv") as f:
        reader = csv.DictReader(f)
        rows = list(reader)
    for row in rows:
        assert row["Derivation"].strip(), (
            f"Empty Derivation for variable {row['Variable']}"
        )
