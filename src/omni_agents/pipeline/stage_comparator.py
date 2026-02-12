"""Stage-by-stage comparison of Track A and Track B pipeline outputs."""

import csv
import json
import math
from collections import Counter
from pathlib import Path

from omni_agents.models.resolution import (
    StageComparison,
    StageComparisonResult,
    TrackResult,
)

# Tolerance specifications for statistical comparisons.
# These mirror the values in ConsensusJudge.TOLERANCES but are defined
# locally to avoid coupling between the two modules.
STATS_TOLERANCES: dict[str, dict] = {
    "n_subjects": {"type": "exact"},
    "n_events": {"type": "exact"},
    "n_censored": {"type": "exact"},
    "logrank_p": {"type": "absolute", "threshold": 1e-3},
    "cox_hr": {"type": "relative", "threshold": 0.001},
    "km_median_treatment": {"type": "absolute", "threshold": 0.5},
    "km_median_placebo": {"type": "absolute", "threshold": 0.5},
}


class StageComparator:
    """Compare Track A and Track B outputs at each pipeline stage.

    All methods are classmethods.  No instance state is needed.
    """

    @staticmethod
    def _read_csv(path: Path) -> list[dict[str, str]]:
        """Read a CSV file into a list of dicts via csv.DictReader."""
        with open(path, newline="") as f:
            reader = csv.DictReader(f)
            return list(reader)

    # ------------------------------------------------------------------
    # SDTM comparison
    # ------------------------------------------------------------------

    @classmethod
    def compare_sdtm(
        cls,
        track_a_dir: Path,
        track_b_dir: Path,
        expected_subjects: int,
    ) -> StageComparison:
        """Compare SDTM DM.csv and VS.csv between two tracks.

        Uses exact-match tolerance (zero) for all checks.

        Args:
            track_a_dir: Directory containing Track A SDTM outputs.
            track_b_dir: Directory containing Track B SDTM outputs.
            expected_subjects: Expected number of unique subjects.

        Returns:
            A :class:`StageComparison` for the ``sdtm`` stage.
        """
        issues: list[str] = []

        dm_a = cls._read_csv(track_a_dir / "DM.csv")
        dm_b = cls._read_csv(track_b_dir / "DM.csv")
        vs_a = cls._read_csv(track_a_dir / "VS.csv")
        vs_b = cls._read_csv(track_b_dir / "VS.csv")

        # 1. DM row count
        if len(dm_a) != len(dm_b):
            issues.append(
                f"DM row count mismatch: Track A={len(dm_a)}, Track B={len(dm_b)}"
            )

        # 2. VS row count
        if len(vs_a) != len(vs_b):
            issues.append(
                f"VS row count mismatch: Track A={len(vs_a)}, Track B={len(vs_b)}"
            )

        # 3. DM column sets
        dm_cols_a = set(dm_a[0].keys()) if dm_a else set()
        dm_cols_b = set(dm_b[0].keys()) if dm_b else set()
        if dm_cols_a != dm_cols_b:
            only_a = dm_cols_a - dm_cols_b
            only_b = dm_cols_b - dm_cols_a
            issues.append(
                f"DM column mismatch: only in A={sorted(only_a)}, "
                f"only in B={sorted(only_b)}"
            )

        # 4. VS column sets
        vs_cols_a = set(vs_a[0].keys()) if vs_a else set()
        vs_cols_b = set(vs_b[0].keys()) if vs_b else set()
        if vs_cols_a != vs_cols_b:
            only_a = vs_cols_a - vs_cols_b
            only_b = vs_cols_b - vs_cols_a
            issues.append(
                f"VS column mismatch: only in A={sorted(only_a)}, "
                f"only in B={sorted(only_b)}"
            )

        # 5. Subject ID set equality
        subj_a = {row["USUBJID"] for row in dm_a}
        subj_b = {row["USUBJID"] for row in dm_b}
        if subj_a != subj_b:
            only_in_a = subj_a - subj_b
            only_in_b = subj_b - subj_a
            issues.append(
                f"Subject ID mismatch: {len(only_in_a)} only in A, "
                f"{len(only_in_b)} only in B"
            )

        # 6. ARM distribution
        arm_a = Counter(row["ARM"] for row in dm_a)
        arm_b = Counter(row["ARM"] for row in dm_b)
        if arm_a != arm_b:
            issues.append(
                f"ARM distribution mismatch: A={dict(arm_a)}, B={dict(arm_b)}"
            )

        # 7. SEX distribution
        sex_a = Counter(row["SEX"] for row in dm_a)
        sex_b = Counter(row["SEX"] for row in dm_b)
        if sex_a != sex_b:
            issues.append(
                f"SEX distribution mismatch: A={dict(sex_a)}, B={dict(sex_b)}"
            )

        # 8. RACE distribution
        race_a = Counter(row["RACE"] for row in dm_a)
        race_b = Counter(row["RACE"] for row in dm_b)
        if race_a != race_b:
            issues.append(
                f"RACE distribution mismatch: A={dict(race_a)}, B={dict(race_b)}"
            )

        track_a_summary = {
            "dm_rows": len(dm_a),
            "vs_rows": len(vs_a),
            "subjects": len(subj_a),
        }
        track_b_summary = {
            "dm_rows": len(dm_b),
            "vs_rows": len(vs_b),
            "subjects": len(subj_b),
        }

        return StageComparison(
            stage="sdtm",
            matches=len(issues) == 0,
            issues=issues,
            track_a_summary=track_a_summary,
            track_b_summary=track_b_summary,
        )

    # ------------------------------------------------------------------
    # ADaM comparison
    # ------------------------------------------------------------------

    @classmethod
    def compare_adam(
        cls,
        track_a_dir: Path,
        track_b_dir: Path,
        expected_subjects: int,
    ) -> StageComparison:
        """Compare ADaM ADTTE_summary.json between two tracks.

        Uses exact-match tolerance for all checks.

        Args:
            track_a_dir: Directory containing Track A ADaM outputs.
            track_b_dir: Directory containing Track B ADaM outputs.
            expected_subjects: Expected number of unique subjects.

        Returns:
            A :class:`StageComparison` for the ``adam`` stage.
        """
        issues: list[str] = []

        summary_a = json.loads((track_a_dir / "ADTTE_summary.json").read_text())
        summary_b = json.loads((track_b_dir / "ADTTE_summary.json").read_text())

        # 1. n_rows
        if summary_a["n_rows"] != summary_b["n_rows"]:
            issues.append(
                f"n_rows mismatch: Track A={summary_a['n_rows']}, "
                f"Track B={summary_b['n_rows']}"
            )

        # 2. n_events
        if summary_a["n_events"] != summary_b["n_events"]:
            issues.append(
                f"n_events mismatch: Track A={summary_a['n_events']}, "
                f"Track B={summary_b['n_events']}"
            )

        # 3. n_censored
        if summary_a["n_censored"] != summary_b["n_censored"]:
            issues.append(
                f"n_censored mismatch: Track A={summary_a['n_censored']}, "
                f"Track B={summary_b['n_censored']}"
            )

        # 4. PARAMCD
        if summary_a["paramcd"] != summary_b["paramcd"]:
            issues.append(
                f"PARAMCD mismatch: Track A='{summary_a['paramcd']}', "
                f"Track B='{summary_b['paramcd']}'"
            )

        # 5. Column sets
        cols_a = set(summary_a["columns"])
        cols_b = set(summary_b["columns"])
        if cols_a != cols_b:
            only_a = cols_a - cols_b
            only_b = cols_b - cols_a
            issues.append(
                f"Column mismatch: only in A={sorted(only_a)}, "
                f"only in B={sorted(only_b)}"
            )

        track_a_summary = {
            "n_rows": summary_a["n_rows"],
            "n_events": summary_a["n_events"],
            "n_censored": summary_a["n_censored"],
            "paramcd": summary_a["paramcd"],
        }
        track_b_summary = {
            "n_rows": summary_b["n_rows"],
            "n_events": summary_b["n_events"],
            "n_censored": summary_b["n_censored"],
            "paramcd": summary_b["paramcd"],
        }

        return StageComparison(
            stage="adam",
            matches=len(issues) == 0,
            issues=issues,
            track_a_summary=track_a_summary,
            track_b_summary=track_b_summary,
        )

    # ------------------------------------------------------------------
    # Stats comparison
    # ------------------------------------------------------------------

    @classmethod
    def compare_stats(
        cls,
        track_a_dir: Path,
        track_b_dir: Path,
    ) -> StageComparison:
        """Compare Stats results.json between two tracks.

        Uses ConsensusJudge-compatible tolerances defined in
        :data:`STATS_TOLERANCES`.

        Args:
            track_a_dir: Directory containing Track A stats outputs.
            track_b_dir: Directory containing Track B stats outputs.

        Returns:
            A :class:`StageComparison` for the ``stats`` stage.
        """
        issues: list[str] = []

        results_a = json.loads((track_a_dir / "results.json").read_text())
        results_b = json.loads((track_b_dir / "results.json").read_text())

        # Extract metric values from both tracks
        metrics: dict[str, tuple[float, float]] = {
            "n_subjects": (
                float(results_a["metadata"]["n_subjects"]),
                float(results_b["metadata"]["n_subjects"]),
            ),
            "n_events": (
                float(results_a["metadata"]["n_events"]),
                float(results_b["metadata"]["n_events"]),
            ),
            "n_censored": (
                float(results_a["metadata"]["n_censored"]),
                float(results_b["metadata"]["n_censored"]),
            ),
            "logrank_p": (
                float(results_a["table2"]["logrank_p"]),
                float(results_b["table2"]["logrank_p"]),
            ),
            "cox_hr": (
                float(results_a["table3"]["cox_hr"]),
                float(results_b["table3"]["cox_hr"]),
            ),
            "km_median_treatment": (
                float(results_a["table2"]["km_median_treatment"]),
                float(results_b["table2"]["km_median_treatment"]),
            ),
            "km_median_placebo": (
                float(results_a["table2"]["km_median_placebo"]),
                float(results_b["table2"]["km_median_placebo"]),
            ),
        }

        track_a_summary: dict[str, object] = {}
        track_b_summary: dict[str, object] = {}

        for metric_name, (val_a, val_b) in metrics.items():
            track_a_summary[metric_name] = val_a
            track_b_summary[metric_name] = val_b

            spec = STATS_TOLERANCES[metric_name]
            tol_type: str = spec["type"]
            threshold: float | None = spec.get("threshold")

            if tol_type == "exact":
                within = val_a == val_b
            elif tol_type == "absolute":
                within = abs(val_a - val_b) <= threshold  # type: ignore[operator]
            elif tol_type == "relative":
                within = math.isclose(
                    val_a, val_b, rel_tol=threshold, abs_tol=0  # type: ignore[arg-type]
                )
            else:
                msg = f"Unknown tolerance type: {tol_type}"
                raise ValueError(msg)

            if not within:
                diff = abs(val_a - val_b)
                issues.append(
                    f"{metric_name} mismatch: Track A={val_a}, Track B={val_b} "
                    f"(diff={diff}, tolerance={tol_type}"
                    + (f" {threshold})" if threshold is not None else ")")
                )

        return StageComparison(
            stage="stats",
            matches=len(issues) == 0,
            issues=issues,
            track_a_summary=track_a_summary,
            track_b_summary=track_b_summary,
        )

    # ------------------------------------------------------------------
    # All-stages aggregator
    # ------------------------------------------------------------------

    @classmethod
    def compare_all_stages(
        cls,
        track_a_result: TrackResult,
        track_b_result: TrackResult,
        expected_subjects: int,
    ) -> StageComparisonResult:
        """Compare all three pipeline stages between two tracks.

        Calls :meth:`compare_sdtm`, :meth:`compare_adam`, and
        :meth:`compare_stats` in sequence and returns a combined result.

        Args:
            track_a_result: Track A pipeline outputs.
            track_b_result: Track B pipeline outputs.
            expected_subjects: Expected number of unique subjects.

        Returns:
            A :class:`StageComparisonResult` aggregating all stage comparisons.
        """
        sdtm = cls.compare_sdtm(
            track_a_result.sdtm_dir,
            track_b_result.sdtm_dir,
            expected_subjects,
        )
        adam = cls.compare_adam(
            track_a_result.adam_dir,
            track_b_result.adam_dir,
            expected_subjects,
        )
        stats = cls.compare_stats(
            track_a_result.stats_dir,
            track_b_result.stats_dir,
        )

        return StageComparisonResult(comparisons=[sdtm, adam, stats])
