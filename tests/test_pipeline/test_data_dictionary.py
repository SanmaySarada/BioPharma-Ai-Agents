"""Tests for deterministic data dictionary generation (DICT-02, DICT-03, DICT-04)."""

import csv
from pathlib import Path

import pytest

from omni_agents.config import TrialConfig
from omni_agents.pipeline.data_dictionary import (
    write_adam_data_dictionary,
    write_sdtm_data_dictionary,
)


def test_sdtm_data_dictionary_creates_file(tmp_path: Path) -> None:
    """SDTM data dictionary file is created in the given directory."""
    write_sdtm_data_dictionary(tmp_path, TrialConfig())
    assert (tmp_path / "data_dictionary.csv").exists()


def test_sdtm_data_dictionary_has_correct_columns(tmp_path: Path) -> None:
    """SDTM data dictionary CSV has exactly the four required columns."""
    write_sdtm_data_dictionary(tmp_path, TrialConfig())
    with open(tmp_path / "data_dictionary.csv") as f:
        reader = csv.DictReader(f)
        # Consume rows so fieldnames is populated
        list(reader)
        assert reader.fieldnames == ["Variable", "Label", "Type", "Derivation"]


def test_sdtm_data_dictionary_contains_dm_and_vs_variables(tmp_path: Path) -> None:
    """SDTM data dictionary contains variables from both DM and VS domains."""
    write_sdtm_data_dictionary(tmp_path, TrialConfig())
    with open(tmp_path / "data_dictionary.csv") as f:
        reader = csv.DictReader(f)
        rows = list(reader)
    variables = [row["Variable"] for row in rows]
    # DM variables
    for var in ("STUDYID", "USUBJID", "AGE", "SEX", "RACE", "ARM"):
        assert var in variables, f"Missing DM variable: {var}"
    # VS variables
    for var in ("VSTESTCD", "VSTEST", "VSSTRESN"):
        assert var in variables, f"Missing VS variable: {var}"


def test_adam_data_dictionary_creates_file(tmp_path: Path) -> None:
    """ADaM data dictionary file is created in the given directory."""
    write_adam_data_dictionary(tmp_path, TrialConfig())
    assert (tmp_path / "data_dictionary.csv").exists()


def test_adam_data_dictionary_has_correct_columns(tmp_path: Path) -> None:
    """ADaM data dictionary CSV has exactly the four required columns."""
    write_adam_data_dictionary(tmp_path, TrialConfig())
    with open(tmp_path / "data_dictionary.csv") as f:
        reader = csv.DictReader(f)
        list(reader)
        assert reader.fieldnames == ["Variable", "Label", "Type", "Derivation"]


def test_adam_data_dictionary_contains_adtte_variables(tmp_path: Path) -> None:
    """ADaM data dictionary contains all expected ADTTE variables."""
    write_adam_data_dictionary(tmp_path, TrialConfig())
    with open(tmp_path / "data_dictionary.csv") as f:
        reader = csv.DictReader(f)
        rows = list(reader)
    variables = [row["Variable"] for row in rows]
    for var in (
        "USUBJID", "PARAMCD", "PARAM", "AVAL", "CNSR",
        "STARTDT", "EVNTDESC", "AGE", "SEX", "ARM",
    ):
        assert var in variables, f"Missing ADTTE variable: {var}"


def test_adam_data_dictionary_uses_event_threshold(tmp_path: Path) -> None:
    """ADaM data dictionary derivation text is parameterized by event_threshold."""
    tc = TrialConfig(treatment_sbp_mean=130.0)
    write_adam_data_dictionary(tmp_path, tc)
    with open(tmp_path / "data_dictionary.csv") as f:
        reader = csv.DictReader(f)
        rows = list(reader)
    derivations = [row["Derivation"] for row in rows]
    assert any(
        "130" in d for d in derivations
    ), "Expected event_threshold (130) in at least one derivation"


def test_sdtm_data_dictionary_returns_path(tmp_path: Path) -> None:
    """write_sdtm_data_dictionary returns the Path to the written CSV."""
    result = write_sdtm_data_dictionary(tmp_path, TrialConfig())
    assert result == tmp_path / "data_dictionary.csv"


def test_data_dictionary_is_deterministic(tmp_path: Path) -> None:
    """Writing the same dictionary twice produces identical output (DICT-04)."""
    dir_a = tmp_path / "a"
    dir_a.mkdir()
    dir_b = tmp_path / "b"
    dir_b.mkdir()

    tc = TrialConfig()
    write_sdtm_data_dictionary(dir_a, tc)
    write_sdtm_data_dictionary(dir_b, tc)

    content_a = (dir_a / "data_dictionary.csv").read_text()
    content_b = (dir_b / "data_dictionary.csv").read_text()
    assert content_a == content_b


def test_adam_data_dictionary_derivation_text_not_empty(tmp_path: Path) -> None:
    """Every ADaM data dictionary row has a non-empty Derivation field."""
    write_adam_data_dictionary(tmp_path, TrialConfig())
    with open(tmp_path / "data_dictionary.csv") as f:
        reader = csv.DictReader(f)
        rows = list(reader)
    for row in rows:
        assert row["Derivation"].strip(), (
            f"Empty Derivation for variable {row['Variable']}"
        )


def test_adam_data_dictionary_contains_adsl_variables(tmp_path: Path) -> None:
    """ADaM data dictionary contains ADSL population flags and treatment vars."""
    write_adam_data_dictionary(tmp_path, TrialConfig())
    with open(tmp_path / "data_dictionary.csv") as f:
        reader = csv.DictReader(f)
        rows = list(reader)
    variables = [row["Variable"] for row in rows]
    for var in (
        "TRT01P", "TRT01A", "SAFFL", "ITTFL", "EFFFL",
        "TRTSDT", "TRTEDT", "TRTDUR", "EOSSTT", "DCSREAS",
        "AGEGR1", "AGEU",
    ):
        assert var in variables, f"Missing ADSL variable: {var}"


def test_adam_data_dictionary_adtte_derivation_references_adsl(tmp_path: Path) -> None:
    """ADTTE variable derivations reference ADSL, not DM directly."""
    write_adam_data_dictionary(tmp_path, TrialConfig())
    with open(tmp_path / "data_dictionary.csv") as f:
        reader = csv.DictReader(f)
        rows = list(reader)
    # Find ADTTE AGE/SEX/ARM/ARMCD derivations (the ones that should say "from ADSL")
    # There are two sets: one for ADSL (from DM) and one for ADTTE (from ADSL)
    # The ADTTE ones appear after PARAMCD and should reference ADSL
    adtte_vars_from_adsl = []
    seen_adtte_section = False
    for row in rows:
        if row["Variable"] == "PARAMCD":
            seen_adtte_section = True
        if seen_adtte_section and row["Variable"] in ("AGE", "SEX", "ARM", "ARMCD"):
            adtte_vars_from_adsl.append(row)
    assert len(adtte_vars_from_adsl) >= 4, "Expected AGE, SEX, ARM, ARMCD in ADTTE section"
    for row in adtte_vars_from_adsl:
        assert "ADSL" in row["Derivation"], (
            f"ADTTE {row['Variable']} derivation should reference ADSL, "
            f"got: {row['Derivation']}"
        )
