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
    REQUIRED_ADSL_COLS,
    REQUIRED_ADTTE_COLS,
    REQUIRED_DM_COLS,
    REQUIRED_VS_COLS,
    STATS_EXPECTED_FILES,
    VALID_RACE,
    VALID_SEX,
    ADSLSummary,
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
        """Validate ADaM ADSL and ADTTE datasets via their JSON summaries.

        Checks:
        - ADSL.csv and ADSL_summary.json exist and validate
        - ADTTE.rds and ADTTE_summary.json exist and validate
        - Row counts match expected subjects
        - Required columns present in both datasets
        - PARAMCD == "TTESB120" for ADTTE

        Args:
            adam_dir: Directory containing ADSL/ADTTE files and summaries.
            expected_subjects: Expected number of unique subjects.

        Raises:
            SchemaValidationError: If any validation check fails.
        """
        issues: list[str] = []

        # --- ADSL checks ---
        adsl_csv_path = adam_dir / "ADSL.csv"
        adsl_summary_path = adam_dir / "ADSL_summary.json"

        if not adsl_csv_path.exists():
            issues.append("ADSL.csv not found in ADaM output directory")
        if not adsl_summary_path.exists():
            issues.append(
                "ADSL_summary.json not found in ADaM output directory"
            )

        # Parse ADSL summary if both files exist
        if adsl_csv_path.exists() and adsl_summary_path.exists():
            try:
                adsl_raw = json.loads(adsl_summary_path.read_text())
                adsl_summary = ADSLSummary(**adsl_raw)
            except (json.JSONDecodeError, ValueError, TypeError) as e:
                issues.append(f"ADSL_summary.json parse error: {e}")
                adsl_summary = None

            if adsl_summary is not None:
                # Row count (one row per subject)
                if adsl_summary.n_rows != expected_subjects:
                    issues.append(
                        f"ADSL: expected {expected_subjects} rows "
                        f"(one per subject), got {adsl_summary.n_rows}"
                    )

                # Column check
                adsl_actual = set(adsl_summary.columns)
                issues.extend(
                    cls._check_columns(
                        adsl_actual, REQUIRED_ADSL_COLS, "ADSL"
                    )
                )

        # --- ADTTE checks ---
        rds_path = adam_dir / "ADTTE.rds"
        summary_path = adam_dir / "ADTTE_summary.json"

        if not rds_path.exists():
            issues.append("ADTTE.rds not found in ADaM output directory")
        if not summary_path.exists():
            issues.append("ADTTE_summary.json not found in ADaM output directory")

        # If ADTTE files are missing, raise now with all collected issues
        if not rds_path.exists() or not summary_path.exists():
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

        # Sanity check: with dropout_rate > 0, having 0 censored subjects is implausible
        if summary.n_censored == 0:
            issues.append(
                "ADTTE: n_censored is 0 — all subjects classified as events. "
                "This likely indicates a bug in event detection logic "
                "(e.g., min(empty, na.rm=TRUE) returning Inf treated as an event). "
                "Expected some censored subjects given dropout rate."
            )

        # Sanity check: event rate above 95% is suspicious for this trial design
        if summary.n_rows > 0:
            event_rate = summary.n_events / summary.n_rows
            if event_rate > 0.95:
                issues.append(
                    f"ADTTE: event rate is {event_rate:.1%} ({summary.n_events}/{summary.n_rows}). "
                    f"Rate above 95% is suspicious — check for Inf in AVAL from "
                    f"min(empty_vector, na.rm=TRUE) being treated as an event."
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
            "ADaM validation passed: ADSL={} rows, ADTTE={} rows, "
            "{} events, {} censored, PARAMCD={}",
            expected_subjects,
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

        logger.info(
            "Stats validation passed: all {} expected files present",
            len(STATS_EXPECTED_FILES),
        )

    @classmethod
    def validate_output_completeness(cls, track_dir: Path) -> None:
        """Validate that all expected output artifacts exist in a track directory.

        Called after all pipeline steps complete for a track. Checks for
        data dictionary files alongside SDTM and ADaM outputs (DICT-05).

        Args:
            track_dir: Root track directory (e.g., output/track_a/).

        Raises:
            SchemaValidationError: If expected output files are missing.
        """
        issues: list[str] = []

        sdtm_dict = track_dir / "sdtm" / "data_dictionary.csv"
        if not sdtm_dict.exists():
            issues.append(
                "sdtm/data_dictionary.csv not found — SDTM data dictionary missing"
            )

        adam_dict = track_dir / "adam" / "data_dictionary.csv"
        if not adam_dict.exists():
            issues.append(
                "adam/data_dictionary.csv not found — ADaM data dictionary missing"
            )

        adsl_csv = track_dir / "adam" / "ADSL.csv"
        if not adsl_csv.exists():
            issues.append(
                "adam/ADSL.csv not found — ADSL subject-level dataset missing"
            )

        if issues:
            raise SchemaValidationError("OutputCompleteness", issues)

        logger.info(
            "Output completeness check passed: data dictionaries and ADSL present"
        )

    @classmethod
    def validate_track_b(cls, track_b_dir: Path) -> None:
        """Validate Track B validation.json structure (DBLP-05).

        Checks:
        - validation.json exists in ``track_b_dir``
        - File contains valid JSON
        - Required top-level keys: validator_p_value, validator_hr, metadata
        - Required metadata subkeys: n_subjects, n_events, n_censored
        - validator_p_value and validator_hr are numeric (int or float)
        - Metadata values are integers

        Args:
            track_b_dir: Directory containing validation.json.

        Raises:
            SchemaValidationError: If any validation check fails.
        """
        issues: list[str] = []

        validation_path = track_b_dir / "validation.json"
        if not validation_path.exists():
            issues.append("validation.json not found in Track B output directory")
            raise SchemaValidationError("Track B", issues)

        # Parse JSON
        try:
            data = json.loads(validation_path.read_text())
        except json.JSONDecodeError as e:
            issues.append(f"validation.json: invalid JSON: {e}")
            raise SchemaValidationError("Track B", issues) from e

        # Required top-level keys
        required_top = {"validator_p_value", "validator_hr", "metadata"}
        missing_top = required_top - set(data.keys())
        if missing_top:
            issues.append(
                f"validation.json: missing required top-level keys: "
                f"{sorted(missing_top)}"
            )

        # Required metadata subkeys
        metadata = data.get("metadata")
        if metadata is None and "metadata" not in missing_top:
            issues.append("validation.json: 'metadata' is null")
        elif isinstance(metadata, dict):
            required_meta = {"n_subjects", "n_events", "n_censored"}
            missing_meta = required_meta - set(metadata.keys())
            if missing_meta:
                issues.append(
                    f"validation.json metadata: missing required keys: "
                    f"{sorted(missing_meta)}"
                )

            # Metadata value type checks (integers)
            for key in ("n_subjects", "n_events", "n_censored"):
                if key in metadata and not isinstance(metadata[key], int):
                    issues.append(
                        f"validation.json metadata.{key}: expected int, "
                        f"got {type(metadata[key]).__name__}"
                    )

        # Numeric type checks for top-level values
        for key in ("validator_p_value", "validator_hr"):
            if key in data and not isinstance(data[key], (int, float)):
                issues.append(
                    f"validation.json {key}: expected numeric, "
                    f"got {type(data[key]).__name__}"
                )

        if issues:
            raise SchemaValidationError("Track B", issues)

        logger.info("Track B validation passed: validation.json structure OK")
