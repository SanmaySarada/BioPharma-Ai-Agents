"""Deterministic data dictionary generation for SDTM and ADaM outputs.

Writes CSV data dictionary files alongside data files in each track's output
directories. Content is static CDISC domain knowledge parameterized by
TrialConfig -- no LLM or Docker execution needed (DICT-04).
"""

import csv
from pathlib import Path

from omni_agents.config import TrialConfig


def write_sdtm_data_dictionary(sdtm_dir: Path, trial_config: TrialConfig) -> Path:
    """Write SDTM variable definitions to sdtm/data_dictionary.csv.

    Covers DM and VS domain variables produced by the SDTM agent.

    Args:
        sdtm_dir: Track's sdtm/ output directory (e.g., output/track_a/sdtm/).
        trial_config: Trial configuration for parameterized derivation text.

    Returns:
        Path to the written data_dictionary.csv file.
    """
    rows = [
        # DM domain variables
        {
            "Variable": "STUDYID",
            "Label": "Study Identifier",
            "Type": "Char",
            "Derivation": "Fixed value assigned to all subjects",
        },
        {
            "Variable": "DOMAIN",
            "Label": "Domain Abbreviation",
            "Type": "Char",
            "Derivation": 'Fixed: "DM"',
        },
        {
            "Variable": "USUBJID",
            "Label": "Unique Subject Identifier",
            "Type": "Char",
            "Derivation": "Study ID prefix + subject number",
        },
        {
            "Variable": "SUBJID",
            "Label": "Subject Identifier",
            "Type": "Char",
            "Derivation": "Original subject identifier from raw data",
        },
        {
            "Variable": "AGE",
            "Label": "Age at Baseline",
            "Type": "Num",
            "Derivation": "Carried from raw data, integer years",
        },
        {
            "Variable": "AGEU",
            "Label": "Age Units",
            "Type": "Char",
            "Derivation": 'Fixed: "YEARS"',
        },
        {
            "Variable": "SEX",
            "Label": "Sex",
            "Type": "Char",
            "Derivation": "Carried from raw data (M/F); CDISC CT",
        },
        {
            "Variable": "RACE",
            "Label": "Race",
            "Type": "Char",
            "Derivation": "Mapped to CDISC controlled terminology from raw data",
        },
        {
            "Variable": "ARM",
            "Label": "Planned Arm",
            "Type": "Char",
            "Derivation": "Treatment arm from randomization (Treatment/Placebo)",
        },
        {
            "Variable": "ARMCD",
            "Label": "Planned Arm Code",
            "Type": "Char",
            "Derivation": "Derived from ARM: TRT or PBO",
        },
        {
            "Variable": "ACTARM",
            "Label": "Actual Arm",
            "Type": "Char",
            "Derivation": "Same as ARM for this study",
        },
        {
            "Variable": "ACTARMCD",
            "Label": "Actual Arm Code",
            "Type": "Char",
            "Derivation": "Same as ARMCD for this study",
        },
        # VS domain variables
        {
            "Variable": "STUDYID",
            "Label": "Study Identifier",
            "Type": "Char",
            "Derivation": "Fixed value assigned to all subjects",
        },
        {
            "Variable": "DOMAIN",
            "Label": "Domain Abbreviation",
            "Type": "Char",
            "Derivation": 'Fixed: "VS"',
        },
        {
            "Variable": "USUBJID",
            "Label": "Unique Subject Identifier",
            "Type": "Char",
            "Derivation": "From DM domain",
        },
        {
            "Variable": "VSSEQ",
            "Label": "Sequence Number",
            "Type": "Num",
            "Derivation": "Row number within each subject, starting at 1",
        },
        {
            "Variable": "VSTESTCD",
            "Label": "Vital Signs Test Short Name",
            "Type": "Char",
            "Derivation": 'Fixed: "SYSBP" (CDISC controlled term)',
        },
        {
            "Variable": "VSTEST",
            "Label": "Vital Signs Test Name",
            "Type": "Char",
            "Derivation": 'Fixed: "Systolic Blood Pressure"',
        },
        {
            "Variable": "VSORRES",
            "Label": "Result in Original Units",
            "Type": "Char",
            "Derivation": "SBP value as character; empty string for missing",
        },
        {
            "Variable": "VSSTRESN",
            "Label": "Result in Standard Units (Numeric)",
            "Type": "Num",
            "Derivation": "SBP value as numeric; NA for missing",
        },
        {
            "Variable": "VSSTRESU",
            "Label": "Standard Units",
            "Type": "Char",
            "Derivation": 'Fixed: "mmHg"',
        },
        {
            "Variable": "VISITNUM",
            "Label": "Visit Number",
            "Type": "Num",
            "Derivation": (
                f"Visit number (0 through {trial_config.visits - 1})"
            ),
        },
        {
            "Variable": "VISIT",
            "Label": "Visit Name",
            "Type": "Char",
            "Derivation": (
                '"Screening" for Visit 0, "Week N" for subsequent visits'
            ),
        },
        {
            "Variable": "VSBLFL",
            "Label": "Baseline Flag",
            "Type": "Char",
            "Derivation": '"Y" for Visit 0 (baseline), empty for others',
        },
    ]

    out_path = sdtm_dir / "data_dictionary.csv"
    fieldnames = ["Variable", "Label", "Type", "Derivation"]

    with open(out_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    return out_path


def write_adam_data_dictionary(adam_dir: Path, trial_config: TrialConfig) -> Path:
    """Write ADaM ADTTE variable definitions to adam/data_dictionary.csv.

    Covers ADTTE dataset variables produced by the ADaM agent.

    Args:
        adam_dir: Track's adam/ output directory (e.g., output/track_a/adam/).
        trial_config: Trial configuration for event_threshold in derivation text.

    Returns:
        Path to the written data_dictionary.csv file.
    """
    event_threshold = int(trial_config.treatment_sbp_mean)

    rows = [
        {
            "Variable": "STUDYID",
            "Label": "Study Identifier",
            "Type": "Char",
            "Derivation": "Fixed study identifier",
        },
        {
            "Variable": "USUBJID",
            "Label": "Unique Subject Identifier",
            "Type": "Char",
            "Derivation": "From DM domain",
        },
        {
            "Variable": "PARAMCD",
            "Label": "Parameter Code",
            "Type": "Char",
            "Derivation": 'Fixed: "TTESB120"',
        },
        {
            "Variable": "PARAM",
            "Label": "Parameter Description",
            "Type": "Char",
            "Derivation": (
                f"Time to First SBP Below {trial_config.endpoint} Threshold"
            ),
        },
        {
            "Variable": "AVAL",
            "Label": "Analysis Value",
            "Type": "Num",
            "Derivation": (
                "Time to event in weeks (VISITNUM of event or censor point)"
            ),
        },
        {
            "Variable": "CNSR",
            "Label": "Censoring Flag",
            "Type": "Num",
            "Derivation": "0 = event occurred, 1 = censored",
        },
        {
            "Variable": "STARTDT",
            "Label": "Time-to-Event Start Date",
            "Type": "Num",
            "Derivation": "0 (baseline, Week 0)",
        },
        {
            "Variable": "EVNTDESC",
            "Label": "Event Description",
            "Type": "Char",
            "Derivation": (
                f'"SBP < {event_threshold} mmHg" for events; '
                f'"Dropout" or "End of study" for censored'
            ),
        },
        {
            "Variable": "AGE",
            "Label": "Age at Baseline",
            "Type": "Num",
            "Derivation": "Carried from DM domain via left_join on USUBJID",
        },
        {
            "Variable": "SEX",
            "Label": "Sex",
            "Type": "Char",
            "Derivation": "Carried from DM domain via left_join on USUBJID",
        },
        {
            "Variable": "ARM",
            "Label": "Planned Arm",
            "Type": "Char",
            "Derivation": "Carried from DM domain via left_join on USUBJID",
        },
        {
            "Variable": "ARMCD",
            "Label": "Planned Arm Code",
            "Type": "Char",
            "Derivation": "Carried from DM domain via left_join on USUBJID",
        },
    ]

    out_path = adam_dir / "data_dictionary.csv"
    fieldnames = ["Variable", "Label", "Type", "Derivation"]

    with open(out_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    return out_path
