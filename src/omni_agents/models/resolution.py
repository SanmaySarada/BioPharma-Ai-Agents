"""Resolution state models for symmetric double programming architecture.

Defines the structured data models for tracking per-stage comparison
results, resolution hints for re-derivation, and resolution outcomes.
Used by the StageComparator, ResolutionLoop, and Orchestrator.
"""

from pathlib import Path

from pydantic import BaseModel


class TrackResult(BaseModel):
    """Result of running one full track pipeline (SDTM -> ADaM -> Stats).

    Each track produces output in three directories (one per pipeline stage)
    and a final results.json file from the Stats stage.

    Attributes:
        track_id: Identifier for this track ("track_a" or "track_b").
        sdtm_dir: Path to the SDTM output directory.
        adam_dir: Path to the ADaM output directory.
        stats_dir: Path to the Stats output directory.
        results_path: Path to the final results.json file.
    """

    track_id: str
    sdtm_dir: Path
    adam_dir: Path
    stats_dir: Path
    results_path: Path


class StageComparison(BaseModel):
    """Result of comparing one pipeline stage between two tracks.

    Contains the comparison outcome for a single stage (sdtm, adam, or stats)
    including whether the outputs match and a list of human-readable
    discrepancy descriptions.

    Attributes:
        stage: Pipeline stage name ("sdtm", "adam", or "stats").
        matches: True if all comparison checks pass for this stage.
        issues: Human-readable list of discrepancies (empty if matches).
        track_a_summary: Summary statistics from Track A output.
        track_b_summary: Summary statistics from Track B output.
    """

    stage: str
    matches: bool
    issues: list[str]
    track_a_summary: dict[str, object]
    track_b_summary: dict[str, object]


class StageComparisonResult(BaseModel):
    """Aggregated result of all stage comparisons between two tracks.

    Wraps the per-stage comparison results and provides convenience
    properties for checking whether any stage disagrees and locating
    the first disagreement.

    Attributes:
        comparisons: List of per-stage comparison results.
    """

    comparisons: list[StageComparison]

    @property
    def has_disagreement(self) -> bool:
        """Return True if any stage comparison has matches=False."""
        return any(not c.matches for c in self.comparisons)

    @property
    def first_disagreement(self) -> StageComparison | None:
        """Return the first stage with matches=False, or None if all agree."""
        for c in self.comparisons:
            if not c.matches:
                return c
        return None


class ResolutionHint(BaseModel):
    """Structured hint for a track that needs to re-derive a stage.

    Provides targeted feedback about what went wrong without revealing
    the other track's full output, preserving track independence during
    the adversarial resolution process.

    Attributes:
        stage: Pipeline stage name ("sdtm", "adam", or "stats").
        discrepancies: Human-readable list of what disagrees between tracks.
        validation_failures: Schema or referential integrity failures found.
        suggested_checks: Specific things to verify in the generated code.
    """

    stage: str
    discrepancies: list[str]
    validation_failures: list[str]
    suggested_checks: list[str]

    def to_prompt_text(self) -> str:
        """Render this hint as structured text for injection into an agent prompt.

        Returns:
            Multi-line string describing the discrepancies, validation failures
            (if any), and suggested checks for the agent to address.
        """
        lines = [
            f"RESOLUTION HINT: Your previous {self.stage} output had "
            f"discrepancies with an independent validation.",
            "",
            "Discrepancies found:",
        ]
        for d in self.discrepancies:
            lines.append(f"  - {d}")

        if self.validation_failures:
            lines.append("")
            lines.append("Validation failures:")
            for v in self.validation_failures:
                lines.append(f"  - {v}")

        lines.append("")
        lines.append("Please check:")
        for s in self.suggested_checks:
            lines.append(f"  - {s}")

        return "\n".join(lines)


class ResolutionResult(BaseModel):
    """Outcome of the resolution loop for a stage-level disagreement.

    Records whether the disagreement was resolved, how many iterations
    were needed, and which track (if any) was selected when resolution
    was unsuccessful.

    Attributes:
        resolved: True if the tracks now agree after resolution.
        iterations: Number of resolution iterations performed.
        winning_track: If not resolved, which track was picked (or None if HALT).
        stage: The pipeline stage that was being resolved.
        resolution_log: Human-readable log of resolution steps taken.
    """

    resolved: bool
    iterations: int
    winning_track: str | None = None
    stage: str
    resolution_log: list[str]
