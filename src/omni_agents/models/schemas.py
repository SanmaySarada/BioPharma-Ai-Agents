"""CDISC column specification constants and validation helpers.

Provides frozenset constants for required columns in SDTM, ADaM, and Stats
outputs, plus CDISC Controlled Terminology value sets and a Pydantic model
for the ADTTE summary JSON produced by the ADaM agent.
"""

from pydantic import BaseModel

# ---------------------------------------------------------------------------
# SDTM Domain Column Requirements
# ---------------------------------------------------------------------------

# DM Domain (Demographics) - SDTM v1.7
REQUIRED_DM_COLS: frozenset[str] = frozenset({
    "STUDYID", "DOMAIN", "USUBJID", "SUBJID",
    "AGE", "AGEU", "SEX", "RACE", "ARM", "ARMCD",
    "ACTARM", "ACTARMCD",
})

# VS Domain (Vital Signs) - SDTMIG v3.3
REQUIRED_VS_COLS: frozenset[str] = frozenset({
    "STUDYID", "DOMAIN", "USUBJID", "VSSEQ",
    "VSTESTCD", "VSTEST", "VSORRES", "VSSTRESN",
    "VSSTRESU", "VISITNUM", "VISIT",
})

# ---------------------------------------------------------------------------
# ADaM Dataset Column Requirements
# ---------------------------------------------------------------------------

# ADTTE Dataset (ADaM BDS-TTE v1.0)
REQUIRED_ADTTE_COLS: frozenset[str] = frozenset({
    "STUDYID", "USUBJID", "PARAMCD", "PARAM",
    "AVAL", "CNSR", "STARTDT", "EVNTDESC",
    "AGE", "SEX", "ARM", "ARMCD",
})

# ---------------------------------------------------------------------------
# CDISC Controlled Terminology
# ---------------------------------------------------------------------------

VALID_SEX: frozenset[str] = frozenset({"M", "F", "U", "UNDIFFERENTIATED"})
VALID_RACE: frozenset[str] = frozenset({
    "WHITE", "BLACK OR AFRICAN AMERICAN", "ASIAN",
    "AMERICAN INDIAN OR ALASKA NATIVE",
    "NATIVE HAWAIIAN OR OTHER PACIFIC ISLANDER",
    "MULTIPLE", "NOT REPORTED", "UNKNOWN",
})

# ---------------------------------------------------------------------------
# Stats Output Expected Files
# ---------------------------------------------------------------------------

STATS_EXPECTED_FILES: frozenset[str] = frozenset({
    "table1_demographics.csv",
    "table2_km_results.csv",
    "table3_cox_results.csv",
    "km_plot.png",
    "results.json",
})

# ---------------------------------------------------------------------------
# Pydantic Models
# ---------------------------------------------------------------------------


class ADTTESummary(BaseModel):
    """Summary of ADTTE dataset for Python-side validation.

    The ADaM agent produces this JSON alongside the ADTTE.rds file so that
    Python can validate the dataset without an RDS dependency.
    """

    n_rows: int
    n_events: int
    n_censored: int
    columns: list[str]
    paramcd: str
