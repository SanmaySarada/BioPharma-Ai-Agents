"""Deterministic consensus comparison of Track A and Track B statistical results."""

import json
import math
from pathlib import Path

from omni_agents.models.consensus import (
    ConsensusVerdict,
    MetricComparison,
    Verdict,
)


class ConsensusHaltError(Exception):
    """Raised when consensus comparison results in a HALT verdict.

    Attributes:
        verdict: The full ConsensusVerdict with per-metric details.
    """

    def __init__(self, verdict: ConsensusVerdict) -> None:
        self.verdict = verdict
        super().__init__(f"Consensus HALT: {verdict.investigation_hints}")


class ConsensusJudge:
    """Deterministic comparator for Track A and Track B statistical results.

    Compares results using metric-specific tolerances and produces a graduated
    PASS / WARNING / HALT verdict.  This is pure Python arithmetic -- no LLM.
    """

    TOLERANCES: dict[str, dict] = {
        "n_subjects": {"type": "exact"},
        "n_events": {"type": "exact"},
        "n_censored": {"type": "exact"},
        "logrank_p": {"type": "absolute", "threshold": 1e-3},
        "cox_hr": {"type": "relative", "threshold": 0.001},  # 0.1%
        "km_median_treatment": {"type": "absolute", "threshold": 0.5},
        "km_median_placebo": {"type": "absolute", "threshold": 0.5},
    }

    SIGNIFICANCE_BOUNDARIES: list[float] = [0.001, 0.01, 0.05]

    STRUCTURAL_METRICS: frozenset[str] = frozenset(
        {"n_subjects", "n_events", "n_censored"}
    )

    @classmethod
    def compare(cls, track_a_path: Path, track_b_path: Path) -> ConsensusVerdict:
        """Compare Track A results.json and Track B validation.json (asymmetric).

        .. deprecated::
            Use :meth:`compare_symmetric` for the symmetric double programming
            architecture where both tracks produce results.json.

        Args:
            track_a_path: Path to Track A ``results.json``.
            track_b_path: Path to Track B ``validation.json``.

        Returns:
            A :class:`ConsensusVerdict` with per-metric comparisons,
            overall verdict, boundary warnings, and investigation hints.
        """
        track_a = json.loads(track_a_path.read_text())
        track_b = json.loads(track_b_path.read_text())

        # ------------------------------------------------------------------
        # 1. Structural pre-check (JUDG-08)
        # ------------------------------------------------------------------
        structural_comparisons: list[MetricComparison] = []
        structural_halt = False

        for metric in sorted(cls.STRUCTURAL_METRICS):
            a_val = float(track_a["metadata"][metric])
            b_val = float(track_b["metadata"][metric])
            comp = cls._compare_metric(metric, a_val, b_val)
            structural_comparisons.append(comp)
            if not comp.within_tolerance:
                structural_halt = True

        if structural_halt:
            return ConsensusVerdict(
                verdict=Verdict.HALT,
                comparisons=structural_comparisons,
                boundary_warnings=[],
                investigation_hints=[
                    "Structural mismatch: Track A and Track B analyzed different "
                    "numbers of subjects/events/censored. Check raw data processing "
                    "logic in both tracks."
                ],
            )

        # ------------------------------------------------------------------
        # 2. Statistical comparisons
        # ------------------------------------------------------------------
        stat_comparisons: list[MetricComparison] = []

        # logrank_p: Track A table2.logrank_p vs Track B validator_p_value
        p_a = float(track_a["table2"]["logrank_p"])
        p_b = float(track_b["validator_p_value"])
        stat_comparisons.append(cls._compare_metric("logrank_p", p_a, p_b))

        # cox_hr: Track A table3.cox_hr vs Track B validator_hr
        hr_a = float(track_a["table3"]["cox_hr"])
        hr_b = float(track_b["validator_hr"])
        stat_comparisons.append(cls._compare_metric("cox_hr", hr_a, hr_b))

        # KM medians (optional -- skip gracefully if Track B doesn't provide)
        if "km_median_treatment" in track_b:
            km_treat_a = float(track_a["table2"]["km_median_treatment"])
            km_treat_b = float(track_b["km_median_treatment"])
            stat_comparisons.append(
                cls._compare_metric("km_median_treatment", km_treat_a, km_treat_b)
            )

        if "km_median_placebo" in track_b:
            km_plac_a = float(track_a["table2"]["km_median_placebo"])
            km_plac_b = float(track_b["km_median_placebo"])
            stat_comparisons.append(
                cls._compare_metric("km_median_placebo", km_plac_a, km_plac_b)
            )

        # ------------------------------------------------------------------
        # 3. Determine per-metric verdict (HALT vs WARNING for out-of-tolerance)
        # ------------------------------------------------------------------
        for comp in stat_comparisons:
            if not comp.within_tolerance:
                if comp.metric == "logrank_p":
                    # Check if p-values cross a significance boundary
                    if cls._crosses_boundary(p_a, p_b):
                        comp.verdict = Verdict.HALT
                    else:
                        comp.verdict = Verdict.WARNING
                elif comp.metric == "cox_hr":
                    # HR: always WARNING (no clinical significance boundary)
                    comp.verdict = Verdict.WARNING
                else:
                    # KM medians: WARNING
                    comp.verdict = Verdict.WARNING

        # ------------------------------------------------------------------
        # 4. Overall verdict: worst of all per-metric verdicts
        # ------------------------------------------------------------------
        all_comparisons = structural_comparisons + stat_comparisons

        has_halt = any(c.verdict == Verdict.HALT for c in all_comparisons)
        has_warning = any(c.verdict == Verdict.WARNING for c in all_comparisons)

        if has_halt:
            overall = Verdict.HALT
        elif has_warning:
            overall = Verdict.WARNING
        else:
            overall = Verdict.PASS

        # ------------------------------------------------------------------
        # 5. Boundary warnings (JUDG-07)
        # ------------------------------------------------------------------
        boundary_warnings = cls._check_boundary_warnings(p_a, p_b)

        # ------------------------------------------------------------------
        # 6. Investigation hints (JUDG-09)
        # ------------------------------------------------------------------
        hints = cls._generate_hints(stat_comparisons)

        return ConsensusVerdict(
            verdict=overall,
            comparisons=all_comparisons,
            boundary_warnings=boundary_warnings,
            investigation_hints=hints,
        )

    @classmethod
    def compare_symmetric(
        cls, track_a_results: Path, track_b_results: Path
    ) -> ConsensusVerdict:
        """Compare two results.json files from symmetric tracks.

        Temporary bridge method until StageComparator replaces ConsensusJudge
        in Plan 04.  Both files have identical structure (table2, table3,
        metadata) since both tracks now run the full SDTM -> ADaM -> Stats
        pipeline.

        Args:
            track_a_results: Path to Track A ``results.json``.
            track_b_results: Path to Track B ``results.json``.

        Returns:
            A :class:`ConsensusVerdict` with per-metric comparisons,
            overall verdict, boundary warnings, and investigation hints.
        """
        track_a = json.loads(track_a_results.read_text())
        track_b = json.loads(track_b_results.read_text())

        # ------------------------------------------------------------------
        # 1. Structural pre-check (JUDG-08)
        # ------------------------------------------------------------------
        structural_comparisons: list[MetricComparison] = []
        structural_halt = False

        for metric in sorted(cls.STRUCTURAL_METRICS):
            a_val = float(track_a["metadata"][metric])
            b_val = float(track_b["metadata"][metric])
            comp = cls._compare_metric(metric, a_val, b_val)
            structural_comparisons.append(comp)
            if not comp.within_tolerance:
                structural_halt = True

        if structural_halt:
            return ConsensusVerdict(
                verdict=Verdict.HALT,
                comparisons=structural_comparisons,
                boundary_warnings=[],
                investigation_hints=[
                    "Structural mismatch: Track A and Track B analyzed different "
                    "numbers of subjects/events/censored. Check raw data processing "
                    "logic in both tracks."
                ],
            )

        # ------------------------------------------------------------------
        # 2. Statistical comparisons (same keys from both results.json)
        # ------------------------------------------------------------------
        stat_comparisons: list[MetricComparison] = []

        # logrank_p: both from table2.logrank_p
        p_a = float(track_a["table2"]["logrank_p"])
        p_b = float(track_b["table2"]["logrank_p"])
        stat_comparisons.append(cls._compare_metric("logrank_p", p_a, p_b))

        # cox_hr: both from table3.cox_hr
        hr_a = float(track_a["table3"]["cox_hr"])
        hr_b = float(track_b["table3"]["cox_hr"])
        stat_comparisons.append(cls._compare_metric("cox_hr", hr_a, hr_b))

        # KM medians (optional -- skip gracefully if either doesn't provide)
        if (
            "km_median_treatment" in track_a.get("table2", {})
            and "km_median_treatment" in track_b.get("table2", {})
        ):
            km_treat_a = float(track_a["table2"]["km_median_treatment"])
            km_treat_b = float(track_b["table2"]["km_median_treatment"])
            stat_comparisons.append(
                cls._compare_metric("km_median_treatment", km_treat_a, km_treat_b)
            )

        if (
            "km_median_placebo" in track_a.get("table2", {})
            and "km_median_placebo" in track_b.get("table2", {})
        ):
            km_plac_a = float(track_a["table2"]["km_median_placebo"])
            km_plac_b = float(track_b["table2"]["km_median_placebo"])
            stat_comparisons.append(
                cls._compare_metric("km_median_placebo", km_plac_a, km_plac_b)
            )

        # ------------------------------------------------------------------
        # 3. Determine per-metric verdict
        # ------------------------------------------------------------------
        for comp in stat_comparisons:
            if not comp.within_tolerance:
                if comp.metric == "logrank_p":
                    if cls._crosses_boundary(p_a, p_b):
                        comp.verdict = Verdict.HALT
                    else:
                        comp.verdict = Verdict.WARNING
                elif comp.metric == "cox_hr":
                    comp.verdict = Verdict.WARNING
                else:
                    comp.verdict = Verdict.WARNING

        # ------------------------------------------------------------------
        # 4. Overall verdict: worst of all per-metric verdicts
        # ------------------------------------------------------------------
        all_comparisons = structural_comparisons + stat_comparisons

        has_halt = any(c.verdict == Verdict.HALT for c in all_comparisons)
        has_warning = any(c.verdict == Verdict.WARNING for c in all_comparisons)

        if has_halt:
            overall = Verdict.HALT
        elif has_warning:
            overall = Verdict.WARNING
        else:
            overall = Verdict.PASS

        # ------------------------------------------------------------------
        # 5. Boundary warnings (JUDG-07)
        # ------------------------------------------------------------------
        boundary_warnings = cls._check_boundary_warnings(p_a, p_b)

        # ------------------------------------------------------------------
        # 6. Investigation hints (JUDG-09)
        # ------------------------------------------------------------------
        hints = cls._generate_hints(stat_comparisons)

        return ConsensusVerdict(
            verdict=overall,
            comparisons=all_comparisons,
            boundary_warnings=boundary_warnings,
            investigation_hints=hints,
        )

    @classmethod
    def _compare_metric(
        cls,
        metric: str,
        a_val: float,
        b_val: float,
    ) -> MetricComparison:
        """Compare a single metric using its tolerance specification.

        Args:
            metric: Metric name (key into :attr:`TOLERANCES`).
            a_val: Track A value.
            b_val: Track B value.

        Returns:
            A :class:`MetricComparison` with tolerance check results.
        """
        spec = cls.TOLERANCES[metric]
        tol_type: str = spec["type"]
        threshold: float | None = spec.get("threshold")

        if tol_type == "exact":
            within = a_val == b_val
            difference = abs(a_val - b_val)
        elif tol_type == "absolute":
            difference = abs(a_val - b_val)
            assert threshold is not None
            within = difference <= threshold
        elif tol_type == "relative":
            assert threshold is not None
            within = math.isclose(a_val, b_val, rel_tol=threshold, abs_tol=0)
            denom = max(abs(a_val), abs(b_val))
            difference = abs(a_val - b_val) / denom if denom > 0 else 0.0
        else:
            msg = f"Unknown tolerance type: {tol_type}"
            raise ValueError(msg)

        return MetricComparison(
            metric=metric,
            track_a_value=a_val,
            track_b_value=b_val,
            difference=difference,
            tolerance_type=tol_type,
            tolerance_threshold=threshold,
            within_tolerance=within,
            verdict=Verdict.PASS if within else Verdict.HALT,
        )

    @classmethod
    def _crosses_boundary(cls, p_a: float, p_b: float) -> bool:
        """Check whether two p-values sit on opposite sides of a significance boundary."""
        for boundary in cls.SIGNIFICANCE_BOUNDARIES:
            a_below = p_a < boundary
            b_below = p_b < boundary
            if a_below != b_below:
                return True
        return False

    @classmethod
    def _check_boundary_warnings(
        cls,
        p_a: float,
        p_b: float,
    ) -> list[str]:
        """Generate boundary warnings when p-values straddle significance thresholds.

        Args:
            p_a: Track A p-value.
            p_b: Track B p-value.

        Returns:
            List of human-readable boundary warning strings.
        """
        warnings: list[str] = []
        for boundary in cls.SIGNIFICANCE_BOUNDARIES:
            a_below = p_a < boundary
            b_below = p_b < boundary
            if a_below != b_below:
                above = "Track B" if a_below else "Track A"
                below = "Track A" if a_below else "Track B"
                warnings.append(
                    f"BOUNDARY_WARNING: p-values straddle {boundary} "
                    f"({below} p={min(p_a, p_b):.6g} < {boundary} <= "
                    f"{above} p={max(p_a, p_b):.6g})"
                )
        return warnings

    @classmethod
    def _generate_hints(
        cls,
        comparisons: list[MetricComparison],
    ) -> list[str]:
        """Generate rule-based investigation hints (JUDG-09).

        Patterns:
        - p-value differs but HR agrees -> different test implementations
        - HR differs but p-value agrees -> different Cox model covariates
        - Both differ -> different event/censoring derivation

        Args:
            comparisons: List of statistical metric comparisons.

        Returns:
            List of investigation hint strings.
        """
        p_ok = True
        hr_ok = True

        for comp in comparisons:
            if comp.metric == "logrank_p" and not comp.within_tolerance:
                p_ok = False
            if comp.metric == "cox_hr" and not comp.within_tolerance:
                hr_ok = False

        hints: list[str] = []

        if not p_ok and hr_ok:
            hints.append(
                "p-value differs but HR agrees: likely different test "
                "implementations or tie-handling methods"
            )
        elif p_ok and not hr_ok:
            hints.append(
                "HR differs but p-value agrees: likely different covariates "
                "in Cox model or different reference level for ARM"
            )
        elif not p_ok and not hr_ok:
            hints.append(
                "Both p-value and HR differ: likely different event/censoring "
                "derivation from raw data"
            )

        return hints
