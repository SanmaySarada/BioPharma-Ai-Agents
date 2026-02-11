"""Consensus verdict models for Track A / Track B comparison.

Defines the structured output of the Consensus Judge: per-metric comparison
results and an overall graduated verdict (PASS / WARNING / HALT).
"""

from enum import StrEnum

from pydantic import BaseModel


class Verdict(StrEnum):
    """Graduated verdict for consensus comparison."""

    PASS = "PASS"
    WARNING = "WARNING"
    HALT = "HALT"


class MetricComparison(BaseModel):
    """Result of comparing a single metric between Track A and Track B."""

    metric: str
    track_a_value: float
    track_b_value: float
    difference: float
    tolerance_type: str  # "exact", "absolute", "relative"
    tolerance_threshold: float | None = None
    within_tolerance: bool
    verdict: Verdict


class ConsensusVerdict(BaseModel):
    """Complete consensus verdict with per-metric details.

    Produced by the ConsensusJudge after comparing Track A results.json
    and Track B validation.json. The overall verdict is the worst of all
    per-metric verdicts.
    """

    verdict: Verdict
    comparisons: list[MetricComparison]
    boundary_warnings: list[str] = []
    investigation_hints: list[str] = []

    def to_diagnostic_report(self) -> dict:
        """Produce a serializable diagnostic report for HALT verdicts (JUDG-06).

        Returns:
            Dict containing all verdict details, suitable for JSON
            serialization and human review.
        """
        return self.model_dump()
