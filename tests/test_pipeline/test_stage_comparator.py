"""Tests for StageComparator: per-stage comparison of Track A and Track B outputs."""

import csv
import json
from pathlib import Path

from omni_agents.models.resolution import TrackResult
from omni_agents.pipeline.stage_comparator import StageComparator


# ---------------------------------------------------------------------------
# Fixture helpers
# ---------------------------------------------------------------------------


def _write_csv(path: Path, rows: list[dict]) -> None:
    """Write a list of dicts to a CSV file using csv.DictWriter."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def _write_json(path: Path, data: dict) -> None:
    """Write dict as JSON to path."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data))


def _make_dm_rows(n: int, arms: dict | None = None) -> list[dict]:
    """Generate n DM rows with realistic CDISC demographics.

    Args:
        n: Number of subjects.
        arms: Optional override dict mapping subject index to ARM value.
              Defaults to 2:1 Treatment:Placebo cycling.

    Returns:
        List of DM row dicts.
    """
    rows = []
    for i in range(n):
        if arms is not None and i in arms:
            arm = arms[i]
        else:
            # 2:1 ratio: indices 0,1 -> Treatment, 2 -> Placebo, ...
            arm = "Treatment" if i % 3 != 2 else "Placebo"
        rows.append({
            "USUBJID": f"SUBJ-{i:03d}",
            "ARM": arm,
            "SEX": "M" if i % 2 == 0 else "F",
            "RACE": "WHITE",
            "AGE": "55",
            "STUDYID": "SBP-001",
            "SITEID": "SITE-01",
        })
    return rows


def _make_vs_rows(dm_rows: list[dict], visits: int = 26) -> list[dict]:
    """Generate VS rows for each DM subject across visits.

    Args:
        dm_rows: DM rows to generate VS data for.
        visits: Number of visits per subject.

    Returns:
        List of VS row dicts.
    """
    rows = []
    for dm in dm_rows:
        for v in range(1, visits + 1):
            rows.append({
                "USUBJID": dm["USUBJID"],
                "VISIT": f"VISIT {v}",
                "VSTESTCD": "SBP",
                "VSSTRESN": "120",
            })
    return rows


def _make_adam_summary(n_rows: int, n_events: int) -> dict:
    """Create an ADTTE_summary.json dict.

    Args:
        n_rows: Total row count.
        n_events: Number of events.

    Returns:
        Summary dict matching ADTTE_summary.json schema.
    """
    return {
        "n_rows": n_rows,
        "n_events": n_events,
        "n_censored": n_rows - n_events,
        "paramcd": "TTESB120",
        "columns": ["USUBJID", "PARAMCD", "AVAL", "CNSR", "ARM", "AGE", "SEX"],
    }


def _make_stats_results(
    p: float = 0.032,
    hr: float = 0.75,
    km_treat: float = 18.5,
    km_plac: float = 14.2,
    n_sub: int = 300,
    n_events: int = 180,
    n_cens: int = 120,
) -> dict:
    """Create a results.json dict matching the Stats output schema.

    Args:
        p: Log-rank p-value.
        hr: Cox hazard ratio.
        km_treat: KM median for treatment arm.
        km_plac: KM median for placebo arm.
        n_sub: Number of subjects.
        n_events: Number of events.
        n_cens: Number of censored.

    Returns:
        Results dict matching results.json schema.
    """
    return {
        "metadata": {
            "n_subjects": n_sub,
            "n_events": n_events,
            "n_censored": n_cens,
        },
        "table2": {
            "logrank_p": p,
            "km_median_treatment": km_treat,
            "km_median_placebo": km_plac,
        },
        "table3": {
            "cox_hr": hr,
        },
    }


# ---------------------------------------------------------------------------
# SDTM tests
# ---------------------------------------------------------------------------


class TestCompareSDTM:
    """Tests for StageComparator.compare_sdtm."""

    def test_sdtm_identical_tracks_match(self, tmp_path: Path) -> None:
        """Identical DM and VS across tracks should report matches=True."""
        dm_rows = _make_dm_rows(300)
        vs_rows = _make_vs_rows(dm_rows)

        for track in ("track_a", "track_b"):
            d = tmp_path / track / "sdtm"
            _write_csv(d / "DM.csv", dm_rows)
            _write_csv(d / "VS.csv", vs_rows)

        result = StageComparator.compare_sdtm(
            tmp_path / "track_a" / "sdtm",
            tmp_path / "track_b" / "sdtm",
            expected_subjects=300,
        )

        assert result.matches is True
        assert result.issues == []
        assert result.stage == "sdtm"

    def test_sdtm_different_row_count(self, tmp_path: Path) -> None:
        """Different DM row counts should report a mismatch."""
        dm_a = _make_dm_rows(300)
        dm_b = _make_dm_rows(298)
        vs_a = _make_vs_rows(dm_a)
        vs_b = _make_vs_rows(dm_b)

        _write_csv(tmp_path / "a" / "DM.csv", dm_a)
        _write_csv(tmp_path / "a" / "VS.csv", vs_a)
        _write_csv(tmp_path / "b" / "DM.csv", dm_b)
        _write_csv(tmp_path / "b" / "VS.csv", vs_b)

        result = StageComparator.compare_sdtm(
            tmp_path / "a", tmp_path / "b", expected_subjects=300,
        )

        assert result.matches is False
        assert any("DM row count" in issue for issue in result.issues)

    def test_sdtm_different_subject_ids(self, tmp_path: Path) -> None:
        """Same count but different USUBJIDs should report Subject ID mismatch."""
        dm_a = _make_dm_rows(300)
        dm_b = _make_dm_rows(300)
        # Modify 2 subjects in Track B
        dm_b[0]["USUBJID"] = "SUBJ-900"
        dm_b[1]["USUBJID"] = "SUBJ-901"

        vs_a = _make_vs_rows(dm_a)
        vs_b = _make_vs_rows(dm_b)

        _write_csv(tmp_path / "a" / "DM.csv", dm_a)
        _write_csv(tmp_path / "a" / "VS.csv", vs_a)
        _write_csv(tmp_path / "b" / "DM.csv", dm_b)
        _write_csv(tmp_path / "b" / "VS.csv", vs_b)

        result = StageComparator.compare_sdtm(
            tmp_path / "a", tmp_path / "b", expected_subjects=300,
        )

        assert result.matches is False
        assert any("Subject ID" in issue for issue in result.issues)

    def test_sdtm_different_arm_distribution(self, tmp_path: Path) -> None:
        """Same subjects but different ARM assignments should report ARM mismatch."""
        dm_a = _make_dm_rows(300)
        dm_b = _make_dm_rows(300)
        # Swap ARM for first 10 subjects in Track B
        for i in range(10):
            dm_b[i]["ARM"] = "Placebo" if dm_a[i]["ARM"] == "Treatment" else "Treatment"

        vs_a = _make_vs_rows(dm_a)
        vs_b = _make_vs_rows(dm_b)

        _write_csv(tmp_path / "a" / "DM.csv", dm_a)
        _write_csv(tmp_path / "a" / "VS.csv", vs_a)
        _write_csv(tmp_path / "b" / "DM.csv", dm_b)
        _write_csv(tmp_path / "b" / "VS.csv", vs_b)

        result = StageComparator.compare_sdtm(
            tmp_path / "a", tmp_path / "b", expected_subjects=300,
        )

        assert result.matches is False
        assert any("ARM distribution" in issue for issue in result.issues)


# ---------------------------------------------------------------------------
# ADaM tests
# ---------------------------------------------------------------------------


class TestCompareADaM:
    """Tests for StageComparator.compare_adam."""

    def test_adam_identical_match(self, tmp_path: Path) -> None:
        """Identical ADTTE summaries should report matches=True."""
        summary = _make_adam_summary(300, 180)

        _write_json(tmp_path / "a" / "ADTTE_summary.json", summary)
        _write_json(tmp_path / "b" / "ADTTE_summary.json", summary)

        result = StageComparator.compare_adam(
            tmp_path / "a", tmp_path / "b", expected_subjects=300,
        )

        assert result.matches is True
        assert result.issues == []
        assert result.stage == "adam"

    def test_adam_different_events(self, tmp_path: Path) -> None:
        """Different n_events should report a mismatch."""
        _write_json(
            tmp_path / "a" / "ADTTE_summary.json",
            _make_adam_summary(300, 180),
        )
        _write_json(
            tmp_path / "b" / "ADTTE_summary.json",
            _make_adam_summary(300, 175),
        )

        result = StageComparator.compare_adam(
            tmp_path / "a", tmp_path / "b", expected_subjects=300,
        )

        assert result.matches is False
        assert any("n_events" in issue for issue in result.issues)


# ---------------------------------------------------------------------------
# Stats tests
# ---------------------------------------------------------------------------


class TestCompareStats:
    """Tests for StageComparator.compare_stats."""

    def test_stats_identical_match(self, tmp_path: Path) -> None:
        """Identical results.json should report matches=True."""
        results = _make_stats_results()

        _write_json(tmp_path / "a" / "results.json", results)
        _write_json(tmp_path / "b" / "results.json", results)

        result = StageComparator.compare_stats(tmp_path / "a", tmp_path / "b")

        assert result.matches is True
        assert result.issues == []
        assert result.stage == "stats"

    def test_stats_within_tolerance(self, tmp_path: Path) -> None:
        """logrank_p differing by 0.0005 (within abs 1e-3) should match."""
        _write_json(
            tmp_path / "a" / "results.json",
            _make_stats_results(p=0.032),
        )
        _write_json(
            tmp_path / "b" / "results.json",
            _make_stats_results(p=0.0325),
        )

        result = StageComparator.compare_stats(tmp_path / "a", tmp_path / "b")

        assert result.matches is True

    def test_stats_outside_tolerance(self, tmp_path: Path) -> None:
        """logrank_p differing by 0.005 (outside abs 1e-3) should NOT match."""
        _write_json(
            tmp_path / "a" / "results.json",
            _make_stats_results(p=0.032),
        )
        _write_json(
            tmp_path / "b" / "results.json",
            _make_stats_results(p=0.037),
        )

        result = StageComparator.compare_stats(tmp_path / "a", tmp_path / "b")

        assert result.matches is False
        assert any("logrank_p" in issue for issue in result.issues)

    def test_stats_exact_metric_mismatch(self, tmp_path: Path) -> None:
        """n_subjects differing should report mismatch (exact tolerance)."""
        _write_json(
            tmp_path / "a" / "results.json",
            _make_stats_results(n_sub=300),
        )
        _write_json(
            tmp_path / "b" / "results.json",
            _make_stats_results(n_sub=298),
        )

        result = StageComparator.compare_stats(tmp_path / "a", tmp_path / "b")

        assert result.matches is False
        assert any("n_subjects" in issue for issue in result.issues)


# ---------------------------------------------------------------------------
# All-stages aggregator tests
# ---------------------------------------------------------------------------


class TestCompareAllStages:
    """Tests for StageComparator.compare_all_stages."""

    def _setup_all_stages(
        self,
        tmp_path: Path,
        *,
        dm_rows_a: list[dict] | None = None,
        dm_rows_b: list[dict] | None = None,
        adam_summary_a: dict | None = None,
        adam_summary_b: dict | None = None,
        stats_results_a: dict | None = None,
        stats_results_b: dict | None = None,
    ) -> tuple[TrackResult, TrackResult]:
        """Set up file fixtures for all three stages and return TrackResults."""
        dm_a = dm_rows_a or _make_dm_rows(300)
        dm_b = dm_rows_b or _make_dm_rows(300)

        vs_a = _make_vs_rows(dm_a)
        vs_b = _make_vs_rows(dm_b)

        adam_a = adam_summary_a or _make_adam_summary(300, 180)
        adam_b = adam_summary_b or _make_adam_summary(300, 180)

        stats_a = stats_results_a or _make_stats_results()
        stats_b = stats_results_b or _make_stats_results()

        # Write Track A
        _write_csv(tmp_path / "a" / "sdtm" / "DM.csv", dm_a)
        _write_csv(tmp_path / "a" / "sdtm" / "VS.csv", vs_a)
        _write_json(tmp_path / "a" / "adam" / "ADTTE_summary.json", adam_a)
        _write_json(tmp_path / "a" / "stats" / "results.json", stats_a)

        # Write Track B
        _write_csv(tmp_path / "b" / "sdtm" / "DM.csv", dm_b)
        _write_csv(tmp_path / "b" / "sdtm" / "VS.csv", vs_b)
        _write_json(tmp_path / "b" / "adam" / "ADTTE_summary.json", adam_b)
        _write_json(tmp_path / "b" / "stats" / "results.json", stats_b)

        track_a = TrackResult(
            track_id="track_a",
            sdtm_dir=tmp_path / "a" / "sdtm",
            adam_dir=tmp_path / "a" / "adam",
            stats_dir=tmp_path / "a" / "stats",
            results_path=tmp_path / "a" / "stats" / "results.json",
        )
        track_b = TrackResult(
            track_id="track_b",
            sdtm_dir=tmp_path / "b" / "sdtm",
            adam_dir=tmp_path / "b" / "adam",
            stats_dir=tmp_path / "b" / "stats",
            results_path=tmp_path / "b" / "stats" / "results.json",
        )

        return track_a, track_b

    def test_all_stages_pass(self, tmp_path: Path) -> None:
        """All stages matching should report has_disagreement=False."""
        track_a, track_b = self._setup_all_stages(tmp_path)

        result = StageComparator.compare_all_stages(track_a, track_b, 300)

        assert result.has_disagreement is False
        assert result.first_disagreement is None
        assert len(result.comparisons) == 3

    def test_first_disagreement_found(self, tmp_path: Path) -> None:
        """SDTM matches but ADaM disagrees: first_disagreement should be adam."""
        track_a, track_b = self._setup_all_stages(
            tmp_path,
            adam_summary_a=_make_adam_summary(300, 180),
            adam_summary_b=_make_adam_summary(300, 170),
        )

        result = StageComparator.compare_all_stages(track_a, track_b, 300)

        assert result.has_disagreement is True
        assert result.first_disagreement is not None
        assert result.first_disagreement.stage == "adam"
