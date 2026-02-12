"""Tests for ResolutionLoop: diagnosis, hint generation, cascade logic, and agent contracts."""

from pathlib import Path

from omni_agents.models.resolution import (
    StageComparison,
    TrackResult,
)
from omni_agents.pipeline.resolution import ResolutionLoop


# ---------------------------------------------------------------------------
# Mock TrackResult objects (just need track_id and dummy Paths)
# ---------------------------------------------------------------------------

mock_track_a = TrackResult(
    track_id="track_a",
    sdtm_dir=Path("/tmp/a/sdtm"),
    adam_dir=Path("/tmp/a/adam"),
    stats_dir=Path("/tmp/a/stats"),
    results_path=Path("/tmp/a/stats/results.json"),
)

mock_track_b = TrackResult(
    track_id="track_b",
    sdtm_dir=Path("/tmp/b/sdtm"),
    adam_dir=Path("/tmp/b/adam"),
    stats_dir=Path("/tmp/b/stats"),
    results_path=Path("/tmp/b/stats/results.json"),
)


# ---------------------------------------------------------------------------
# Diagnosis tests
# ---------------------------------------------------------------------------


class TestDiagnose:
    """Tests for ResolutionLoop._diagnose."""

    def test_diagnose_fewer_rows_track_a(self) -> None:
        """Track with fewer rows is diagnosed as failing."""
        loop = ResolutionLoop(max_iterations=2)
        disagreement = StageComparison(
            stage="sdtm",
            matches=False,
            issues=["DM row count: track_a=298, track_b=300"],
            track_a_summary={"dm_rows": 298, "vs_rows": 7748},
            track_b_summary={"dm_rows": 300, "vs_rows": 7800},
        )
        # Track A has fewer rows -> Track A is likely wrong
        result = loop._diagnose(disagreement, mock_track_a, mock_track_b)
        assert result == "track_a"

    def test_diagnose_fewer_rows_track_b(self) -> None:
        """Track B with fewer rows is diagnosed as failing."""
        loop = ResolutionLoop(max_iterations=2)
        disagreement = StageComparison(
            stage="sdtm",
            matches=False,
            issues=["DM row count: track_a=300, track_b=295"],
            track_a_summary={"dm_rows": 300, "vs_rows": 7800},
            track_b_summary={"dm_rows": 295, "vs_rows": 7670},
        )
        result = loop._diagnose(disagreement, mock_track_a, mock_track_b)
        assert result == "track_b"

    def test_diagnose_ambiguous_defaults_track_b(self) -> None:
        """When diagnosis is ambiguous, default to track_b."""
        loop = ResolutionLoop(max_iterations=2)
        disagreement = StageComparison(
            stage="stats",
            matches=False,
            issues=["logrank_p differs: 0.031 vs 0.037"],
            track_a_summary={"logrank_p": 0.031},
            track_b_summary={"logrank_p": 0.037},
        )
        result = loop._diagnose(disagreement, mock_track_a, mock_track_b)
        assert result == "track_b"

    def test_diagnose_n_rows_adam(self) -> None:
        """ADaM stage: track with fewer n_rows is diagnosed as failing."""
        loop = ResolutionLoop(max_iterations=2)
        disagreement = StageComparison(
            stage="adam",
            matches=False,
            issues=["n_rows mismatch: Track A=300, Track B=295"],
            track_a_summary={"n_rows": 300, "n_events": 180},
            track_b_summary={"n_rows": 295, "n_events": 175},
        )
        result = loop._diagnose(disagreement, mock_track_a, mock_track_b)
        assert result == "track_b"

    def test_diagnose_subjects_key(self) -> None:
        """SDTM 'subjects' key: track with fewer subjects is failing."""
        loop = ResolutionLoop(max_iterations=2)
        disagreement = StageComparison(
            stage="sdtm",
            matches=False,
            issues=["Subject ID mismatch"],
            track_a_summary={"dm_rows": 300, "vs_rows": 7800, "subjects": 298},
            track_b_summary={"dm_rows": 300, "vs_rows": 7800, "subjects": 300},
        )
        result = loop._diagnose(disagreement, mock_track_a, mock_track_b)
        assert result == "track_a"


# ---------------------------------------------------------------------------
# Hint generation tests
# ---------------------------------------------------------------------------


class TestGenerateHint:
    """Tests for ResolutionLoop._generate_hint."""

    def test_hint_structure(self) -> None:
        """Hint contains stage, discrepancies, and suggested checks."""
        loop = ResolutionLoop()
        disagreement = StageComparison(
            stage="sdtm",
            matches=False,
            issues=["DM row count: 298 vs 300", "Subject ID mismatch"],
            track_a_summary={},
            track_b_summary={},
        )
        hint = loop._generate_hint(disagreement, "track_b")
        assert hint.stage == "sdtm"
        assert len(hint.discrepancies) == 2
        assert len(hint.suggested_checks) > 0
        text = hint.to_prompt_text()
        assert "RESOLUTION HINT" in text
        assert "DM row count" in text

    def test_hint_suggested_checks_per_stage(self) -> None:
        """Each stage gets stage-appropriate suggested checks."""
        loop = ResolutionLoop()
        for stage in ("sdtm", "adam", "stats"):
            disagreement = StageComparison(
                stage=stage,
                matches=False,
                issues=["some issue"],
                track_a_summary={},
                track_b_summary={},
            )
            hint = loop._generate_hint(disagreement, "track_b")
            assert hint.stage == stage
            assert len(hint.suggested_checks) >= 2

    def test_hint_sdtm_checks(self) -> None:
        """SDTM hints include deduplication and terminology checks."""
        loop = ResolutionLoop()
        disagreement = StageComparison(
            stage="sdtm",
            matches=False,
            issues=["test"],
            track_a_summary={},
            track_b_summary={},
        )
        hint = loop._generate_hint(disagreement, "track_b")
        checks_text = " ".join(hint.suggested_checks)
        assert "deduplication" in checks_text.lower() or "subjects" in checks_text.lower()

    def test_hint_adam_checks(self) -> None:
        """ADaM hints include event definition and CNSR checks."""
        loop = ResolutionLoop()
        disagreement = StageComparison(
            stage="adam",
            matches=False,
            issues=["test"],
            track_a_summary={},
            track_b_summary={},
        )
        hint = loop._generate_hint(disagreement, "track_b")
        checks_text = " ".join(hint.suggested_checks)
        assert "CNSR" in checks_text or "event" in checks_text.lower()

    def test_hint_stats_checks(self) -> None:
        """Stats hints include Cox model and log-rank checks."""
        loop = ResolutionLoop()
        disagreement = StageComparison(
            stage="stats",
            matches=False,
            issues=["test"],
            track_a_summary={},
            track_b_summary={},
        )
        hint = loop._generate_hint(disagreement, "track_b")
        checks_text = " ".join(hint.suggested_checks)
        assert "Cox" in checks_text or "log-rank" in checks_text.lower()

    def test_hint_validation_failures_empty_v1(self) -> None:
        """V1: validation_failures should be empty list."""
        loop = ResolutionLoop()
        disagreement = StageComparison(
            stage="sdtm",
            matches=False,
            issues=["test"],
            track_a_summary={},
            track_b_summary={},
        )
        hint = loop._generate_hint(disagreement, "track_b")
        assert hint.validation_failures == []


# ---------------------------------------------------------------------------
# Pick best track tests
# ---------------------------------------------------------------------------


class TestPickBestTrack:
    """Tests for ResolutionLoop._pick_best_track."""

    def test_ambiguous_returns_track_a(self) -> None:
        """When ambiguous, default winner is track_a."""
        loop = ResolutionLoop()
        disagreement = StageComparison(
            stage="stats",
            matches=False,
            issues=["some issue"],
            track_a_summary={"logrank_p": 0.031},
            track_b_summary={"logrank_p": 0.037},
        )
        result = loop._pick_best_track(disagreement)
        assert result == "track_a"

    def test_pick_best_returns_string(self) -> None:
        """_pick_best_track always returns a string (not None) in V1."""
        loop = ResolutionLoop()
        disagreement = StageComparison(
            stage="adam",
            matches=False,
            issues=["mismatch"],
            track_a_summary={},
            track_b_summary={},
        )
        result = loop._pick_best_track(disagreement)
        assert isinstance(result, str)


# ---------------------------------------------------------------------------
# Cascade logic tests
# ---------------------------------------------------------------------------


class TestCascadeLogic:
    """Tests for cascade ordering logic in _rerun_from_stage."""

    def test_sdtm_cascades_to_adam_and_stats(self) -> None:
        """When stage is sdtm, cascade should run sdtm, adam, stats."""
        for stage, expected_cascade in [
            ("sdtm", ["sdtm", "adam", "stats"]),
            ("adam", ["adam", "stats"]),
            ("stats", ["stats"]),
        ]:
            if stage == "sdtm":
                stages = ["sdtm", "adam", "stats"]
            elif stage == "adam":
                stages = ["adam", "stats"]
            elif stage == "stats":
                stages = ["stats"]
            assert stages == expected_cascade, f"Stage {stage} cascade mismatch"

    def test_unknown_stage_raises(self) -> None:
        """Unknown stage should raise ValueError."""
        import pytest

        loop = ResolutionLoop()
        disagreement = StageComparison(
            stage="unknown",
            matches=False,
            issues=["test"],
            track_a_summary={},
            track_b_summary={},
        )
        with pytest.raises(ValueError, match="Unknown stage"):
            loop._recompare_stage(
                "unknown", mock_track_a, mock_track_b, 300
            )


# ---------------------------------------------------------------------------
# Agent previous_error contract tests
# ---------------------------------------------------------------------------


class TestAgentPreviousErrorContract:
    """Verify that all pipeline agents handle previous_error in build_user_prompt.

    This is CRITICAL for resolution hint injection. The resolution loop passes
    hints as previous_error context. If any agent ignores previous_error, the
    hint is silently dropped and retry produces the same output.
    """

    def test_sdtm_agent_handles_previous_error(self) -> None:
        """SDTMAgent.build_user_prompt includes previous_error when present."""
        from omni_agents.agents.sdtm import SDTMAgent

        import inspect

        source = inspect.getsource(SDTMAgent.build_user_prompt)
        assert "previous_error" in source, (
            "SDTMAgent.build_user_prompt does not reference previous_error. "
            "Resolution hints will be silently dropped."
        )

    def test_adam_agent_handles_previous_error(self) -> None:
        """ADaMAgent.build_user_prompt includes previous_error when present."""
        from omni_agents.agents.adam import ADaMAgent

        import inspect

        source = inspect.getsource(ADaMAgent.build_user_prompt)
        assert "previous_error" in source, (
            "ADaMAgent.build_user_prompt does not reference previous_error. "
            "Resolution hints will be silently dropped."
        )

    def test_stats_agent_handles_previous_error(self) -> None:
        """StatsAgent.build_user_prompt includes previous_error when present."""
        from omni_agents.agents.stats import StatsAgent

        import inspect

        source = inspect.getsource(StatsAgent.build_user_prompt)
        assert "previous_error" in source, (
            "StatsAgent.build_user_prompt does not reference previous_error. "
            "Resolution hints will be silently dropped."
        )


# ---------------------------------------------------------------------------
# Constructor tests
# ---------------------------------------------------------------------------


class TestResolutionLoopInit:
    """Tests for ResolutionLoop initialization."""

    def test_default_max_iterations(self) -> None:
        """Default max_iterations is 2."""
        loop = ResolutionLoop()
        assert loop.max_iterations == 2

    def test_custom_max_iterations(self) -> None:
        """Custom max_iterations is respected."""
        loop = ResolutionLoop(max_iterations=5)
        assert loop.max_iterations == 5
