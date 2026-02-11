"""Inter-agent schema validation for SDTM, ADaM, and Stats outputs.

Validates outputs between pipeline agent handoffs (PIPE-06) to prevent
cascading errors. Each validator checks column presence, row counts,
CDISC controlled terminology, referential integrity, and file structure.
"""

import csv
import json
from pathlib import Path

from loguru import logger

from omni_agents.models.schemas import (
    REQUIRED_ADTTE_COLS,
    REQUIRED_DM_COLS,
    REQUIRED_VS_COLS,
    STATS_EXPECTED_FILES,
    VALID_RACE,
    VALID_SEX,
    ADTTESummary,
)


class SchemaValidationError(Exception):
    """Raised when inter-agent schema validation fails.

    Attributes:
        agent: Name of the agent whose output failed validation.
        issues: List of human-readable issue descriptions.
    """

    def __init__(self, agent: str, issues: list[str]) -> None:
        self.agent = agent
        self.issues = issues
        issue_list = "\n".join(f"  - {issue}" for issue in issues)
        message = (
            f"Schema validation failed for [{agent}] output "
            f"({len(issues)} issue{'s' if len(issues) != 1 else ''}):\n{issue_list}"
        )
        super().__init__(message)


class SchemaValidator:
    """Validates inter-agent output schemas.

    All methods are classmethods that raise SchemaValidationError on failure
    or return None on success (with a loguru info message).
    """

    @staticmethod
    def _read_csv(path: Path) -> list[dict[str, str]]:
        """Read a CSV file into a list of dicts via csv.DictReader."""
        with open(path, newline="") as f:
            reader = csv.DictReader(f)
            return list(reader)

    @staticmethod
    def _check_columns(
        actual: set[str],
        required: frozenset[str],
        label: str,
    ) -> list[str]:
        """Return issue strings for any missing required columns."""
        missing = required - actual
        if missing:
            sorted_missing = sorted(missing)
            return [f"{label}: missing required columns: {sorted_missing}"]
        return []

    @classmethod
    def validate_sdtm(
        cls,
        sdtm_dir: Path,
        expected_subjects: int,
    ) -> None:
        """Validate SDTM DM and VS datasets.

        Checks:
        - DM.csv and VS.csv exist
        - Required columns present
        - Row counts match expected values
        - DM.SEX and DM.RACE use valid CDISC controlled terminology
        - Referential integrity: every VS.USUBJID exists in DM.USUBJID

        Args:
            sdtm_dir: Directory containing DM.csv and VS.csv.
            expected_subjects: Expected number of unique subjects.

        Raises:
            SchemaValidationError: If any validation check fails.
        """
        issues: list[str] = []

        # File existence
        dm_path = sdtm_dir / "DM.csv"
        vs_path = sdtm_dir / "VS.csv"

        if not dm_path.exists():
            issues.append("DM.csv not found in SDTM output directory")
        if not vs_path.exists():
            issues.append("VS.csv not found in SDTM output directory")

        if issues:
            raise SchemaValidationError("SDTM", issues)

        # Read datasets
        dm_rows = cls._read_csv(dm_path)
        vs_rows = cls._read_csv(vs_path)

        # Column checks
        dm_cols = set(dm_rows[0].keys()) if dm_rows else set()
        vs_cols = set(vs_rows[0].keys()) if vs_rows else set()

        issues.extend(cls._check_columns(dm_cols, REQUIRED_DM_COLS, "DM"))
        issues.extend(cls._check_columns(vs_cols, REQUIRED_VS_COLS, "VS"))

        # Row count checks
        if len(dm_rows) != expected_subjects:
            issues.append(
                f"DM: expected {expected_subjects} rows, got {len(dm_rows)}"
            )

        expected_vs_rows = expected_subjects * 26  # 26 visits
        if len(vs_rows) != expected_vs_rows:
            issues.append(
                f"VS: expected {expected_vs_rows} rows "
                f"({expected_subjects} subjects x 26 visits), got {len(vs_rows)}"
            )

        # CDISC Controlled Terminology checks (only if SEX/RACE columns exist)
        if "SEX" in dm_cols:
            invalid_sex = {
                row["SEX"]
                for row in dm_rows
                if row["SEX"] not in VALID_SEX
            }
            if invalid_sex:
                issues.append(
                    f"DM.SEX: invalid values {sorted(invalid_sex)}; "
                    f"allowed: {sorted(VALID_SEX)}"
                )

        if "RACE" in dm_cols:
            invalid_race = {
                row["RACE"]
                for row in dm_rows
                if row["RACE"] not in VALID_RACE
            }
            if invalid_race:
                issues.append(
                    f"DM.RACE: invalid values {sorted(invalid_race)}; "
                    f"allowed: {sorted(VALID_RACE)}"
                )

        # Referential integrity: VS.USUBJID must be subset of DM.USUBJID
        if "USUBJID" in dm_cols and "USUBJID" in vs_cols:
            dm_subjects = {row["USUBJID"] for row in dm_rows}
            vs_subjects = {row["USUBJID"] for row in vs_rows}
            orphan_subjects = vs_subjects - dm_subjects
            if orphan_subjects:
                sample = sorted(orphan_subjects)[:5]
                issues.append(
                    f"Referential integrity: {len(orphan_subjects)} VS subjects "
                    f"not in DM (first 5: {sample})"
                )

        if issues:
            raise SchemaValidationError("SDTM", issues)

        logger.info(
            "SDTM validation passed: DM={} rows, VS={} rows, "
            "{} subjects, referential integrity OK",
            len(dm_rows),
            len(vs_rows),
            expected_subjects,
        )

    @classmethod
    def validate_adam(
        cls,
        adam_dir: Path,
        expected_subjects: int,
    ) -> None:
        """Validate ADaM ADTTE dataset via its JSON summary.

        Checks:
        - ADTTE.rds file exists
        - ADTTE_summary.json exists and parses into ADTTESummary
        - Row count matches expected subjects
        - Events + censored == total subjects
        - Required ADTTE columns present
        - PARAMCD == "TTESB120"

        Args:
            adam_dir: Directory containing ADTTE.rds and ADTTE_summary.json.
            expected_subjects: Expected number of unique subjects.

        Raises:
            SchemaValidationError: If any validation check fails.
        """
        issues: list[str] = []

        rds_path = adam_dir / "ADTTE.rds"
        summary_path = adam_dir / "ADTTE_summary.json"

        if not rds_path.exists():
            issues.append("ADTTE.rds not found in ADaM output directory")
        if not summary_path.exists():
            issues.append("ADTTE_summary.json not found in ADaM output directory")

        if issues:
            raise SchemaValidationError("ADaM", issues)

        # Parse summary JSON
        try:
            raw = json.loads(summary_path.read_text())
            summary = ADTTESummary(**raw)
        except (json.JSONDecodeError, ValueError, TypeError) as e:
            issues.append(f"ADTTE_summary.json parse error: {e}")
            raise SchemaValidationError("ADaM", issues) from e

        # Row count
        if summary.n_rows != expected_subjects:
            issues.append(
                f"ADTTE: expected {expected_subjects} rows, got {summary.n_rows}"
            )

        # Events + censored == total
        total = summary.n_events + summary.n_censored
        if total != expected_subjects:
            issues.append(
                f"ADTTE: n_events ({summary.n_events}) + n_censored "
                f"({summary.n_censored}) = {total}, expected {expected_subjects}"
            )

        # Column check
        actual_cols = set(summary.columns)
        issues.extend(
            cls._check_columns(actual_cols, REQUIRED_ADTTE_COLS, "ADTTE")
        )

        # PARAMCD
        if summary.paramcd != "TTESB120":
            issues.append(
                f"ADTTE.PARAMCD: expected 'TTESB120', got '{summary.paramcd}'"
            )

        if issues:
            raise SchemaValidationError("ADaM", issues)

        logger.info(
            "ADaM validation passed: {} rows, {} events, {} censored, "
            "PARAMCD={}",
            summary.n_rows,
            summary.n_events,
            summary.n_censored,
            summary.paramcd,
        )

    @classmethod
    def validate_stats(cls, stats_dir: Path) -> None:
        """Validate Stats agent outputs.

        Checks:
        - All expected files exist (tables, plot, results.json)
        - results.json is valid JSON with required keys
        - km_plot.png is non-empty

        Args:
            stats_dir: Directory containing stats output files.

        Raises:
            SchemaValidationError: If any validation check fails.
        """
        issues: list[str] = []

        # File existence
        for filename in sorted(STATS_EXPECTED_FILES):
            filepath = stats_dir / filename
            if not filepath.exists():
                issues.append(f"Missing expected file: {filename}")

        # results.json structure
        results_path = stats_dir / "results.json"
        if results_path.exists():
            try:
                data = json.loads(results_path.read_text())
            except json.JSONDecodeError as e:
                issues.append(f"results.json: invalid JSON: {e}")
                data = None

            if data is not None:
                if "table2" not in data:
                    issues.append("results.json: missing 'table2' key")
                elif "logrank_p" not in data["table2"]:
                    issues.append(
                        "results.json: missing 'table2.logrank_p' key"
                    )

                if "table3" not in data:
                    issues.append("results.json: missing 'table3' key")
                elif "cox_hr" not in data["table3"]:
                    issues.append("results.json: missing 'table3.cox_hr' key")

        # km_plot.png non-empty
        plot_path = stats_dir / "km_plot.png"
        if plot_path.exists() and plot_path.stat().st_size == 0:
            issues.append("km_plot.png: file is empty (0 bytes)")

        if issues:
            raise SchemaValidationError("Stats", issues)

        logger.info("Stats validation passed: all {} expected files present", len(STATS_EXPECTED_FILES))
