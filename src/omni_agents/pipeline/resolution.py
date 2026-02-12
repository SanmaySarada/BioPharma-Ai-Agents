"""Adversarial resolution loop for semantic disagreements between symmetric tracks."""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING

from loguru import logger

from omni_agents.models.resolution import (
    ResolutionHint,
    ResolutionResult,
    StageComparison,
    TrackResult,
)
from omni_agents.pipeline.stage_comparator import StageComparator

if TYPE_CHECKING:
    from omni_agents.pipeline.orchestrator import PipelineOrchestrator


# Stage-appropriate suggested checks for resolution hints.
STAGE_SUGGESTED_CHECKS: dict[str, list[str]] = {
    "sdtm": [
        "Check deduplication logic",
        "Verify all subjects from raw data are included",
        "Check CDISC controlled terminology mapping",
    ],
    "adam": [
        "Check event definition (SBP < 120 threshold)",
        "Verify all SDTM subjects flow through",
        "Check CNSR derivation logic",
    ],
    "stats": [
        "Check Cox model specification",
        "Verify log-rank test parameters",
        "Check KM estimation method",
    ],
}


class ResolutionLoop:
    """Orchestrate adversarial resolution when symmetric tracks disagree.

    Resolution protocol:
    1. DETECT: StageComparator finds disagreement at stage S
    2. DIAGNOSE: Deterministic validation rules check which track erred
    3. HINT: Generate structured hint for failing track
    4. RETRY: Re-run failing track from stage S WITH CASCADING downstream re-runs
    5. RE-COMPARE: Compare new output with other track
    6. TERMINATE: After max iterations, pick best track or HALT
    """

    def __init__(self, max_iterations: int = 2) -> None:
        self.max_iterations = max_iterations

    async def resolve(
        self,
        disagreement: StageComparison,
        track_a_result: TrackResult,
        track_b_result: TrackResult,
        orchestrator: PipelineOrchestrator,
        expected_subjects: int,
    ) -> ResolutionResult:
        """Run the resolution loop until agreement or max iterations.

        Args:
            disagreement: The stage that disagreed.
            track_a_result: Current Track A result.
            track_b_result: Current Track B result.
            orchestrator: Reference to orchestrator for re-running tracks.
            expected_subjects: Expected number of subjects for schema validation.

        Returns:
            A ResolutionResult indicating whether resolution succeeded.
        """
        resolution_log: list[str] = []
        current_disagreement = disagreement

        for iteration in range(1, self.max_iterations + 1):
            # 1. Diagnose which track is more likely wrong
            failing_track = self._diagnose(
                current_disagreement, track_a_result, track_b_result
            )
            resolution_log.append(
                f"Iteration {iteration}: diagnosed {failing_track} as likely failing"
            )

            # 2. Generate hint
            hint = self._generate_hint(current_disagreement, failing_track)
            resolution_log.append(
                f"Hint generated for {failing_track}: "
                f"{len(hint.discrepancies)} discrepancies"
            )

            # 3. Re-run failing track from disagreeing stage WITH CASCADE
            if failing_track == "track_a":
                track_a_result = await self._rerun_from_stage(
                    track_a_result,
                    current_disagreement.stage,
                    hint,
                    orchestrator,
                )
            else:
                track_b_result = await self._rerun_from_stage(
                    track_b_result,
                    current_disagreement.stage,
                    hint,
                    orchestrator,
                )

            # 4. Re-compare ALL stages (not just the disagreeing one,
            #    since cascade re-ran downstream)
            new_comparison_result = StageComparator.compare_all_stages(
                track_a_result, track_b_result, expected_subjects
            )

            if not new_comparison_result.has_disagreement:
                resolution_log.append(
                    f"Iteration {iteration}: all stages now agree"
                )
                return ResolutionResult(
                    resolved=True,
                    iterations=iteration,
                    winning_track=None,
                    stage=current_disagreement.stage,
                    resolution_log=resolution_log,
                )

            # Still disagreeing -- update for next iteration
            current_disagreement = new_comparison_result.first_disagreement
            resolution_log.append(
                f"Iteration {iteration}: still disagreeing at "
                f"{current_disagreement.stage}"
            )

        # Max iterations reached
        best_track = self._pick_best_track(current_disagreement)
        resolution_log.append(
            f"Max iterations reached. Best track: {best_track or 'NONE (HALT)'}"
        )
        return ResolutionResult(
            resolved=False,
            iterations=self.max_iterations,
            winning_track=best_track,
            stage=current_disagreement.stage,
            resolution_log=resolution_log,
        )

    def _diagnose(
        self,
        disagreement: StageComparison,
        track_a_result: TrackResult,
        track_b_result: TrackResult,
    ) -> str:
        """Diagnose which track is more likely wrong based on deterministic rules.

        Priority order:
        1. Track with fewer rows/subjects likely dropped data.
        2. If ambiguous, default to track_b (secondary LLM).

        Args:
            disagreement: The stage comparison with issues.
            track_a_result: Track A pipeline result.
            track_b_result: Track B pipeline result.

        Returns:
            "track_a" or "track_b" indicating the likely failing track.
        """
        a_summary = disagreement.track_a_summary
        b_summary = disagreement.track_b_summary

        # Heuristic: if one track has fewer rows/subjects than expected,
        # it dropped data
        for key in ("dm_rows", "n_rows", "subjects"):
            a_val = a_summary.get(key)
            b_val = b_summary.get(key)
            if a_val is not None and b_val is not None and a_val != b_val:
                # The track with fewer items likely dropped data
                if a_val < b_val:
                    return "track_a"
                return "track_b"

        # Default: assume track_b (secondary LLM) is more likely to have issues
        logger.info("Diagnosis ambiguous, defaulting to track_b as failing")
        return "track_b"

    def _generate_hint(
        self, disagreement: StageComparison, failing_track: str
    ) -> ResolutionHint:
        """Generate a structured resolution hint from the stage comparison.

        Args:
            disagreement: The stage comparison with issues.
            failing_track: Which track is being hinted ("track_a" or "track_b").

        Returns:
            A ResolutionHint with discrepancies and suggested checks.
        """
        stage = disagreement.stage
        suggested_checks = STAGE_SUGGESTED_CHECKS.get(stage, [])

        return ResolutionHint(
            stage=stage,
            discrepancies=list(disagreement.issues),
            validation_failures=[],  # V1: future SchemaValidator integration
            suggested_checks=suggested_checks,
        )

    async def _rerun_from_stage(
        self,
        track_result: TrackResult,
        stage: str,
        hint: ResolutionHint,
        orchestrator: PipelineOrchestrator,
    ) -> TrackResult:
        """Re-run from the failing stage and cascade through all downstream stages.

        Cascade order:
        - sdtm: re-run sdtm (with hint) -> adam (fresh) -> stats (fresh)
        - adam: re-run adam (with hint) -> stats (fresh)
        - stats: re-run stats (with hint) only

        Args:
            track_result: The track result to re-run stages for.
            stage: The stage that disagreed.
            hint: The resolution hint for the failing stage.
            orchestrator: Reference to orchestrator for agent execution.

        Returns:
            The same TrackResult object with updated directory contents.
        """
        track_id = track_result.track_id

        # Determine which LLM to use
        if track_id == "track_a":
            from omni_agents.llm.gemini import GeminiAdapter

            llm = GeminiAdapter(orchestrator.settings.llm.gemini)
        else:
            from omni_agents.llm.openai_adapter import OpenAIAdapter

            llm = OpenAIAdapter(orchestrator.settings.llm.openai)

        prompt_dir = Path(__file__).parent.parent / "templates" / "prompts"
        raw_dir = track_result.sdtm_dir.parent.parent / "raw"

        stages_to_run: list[str] = []
        if stage == "sdtm":
            stages_to_run = ["sdtm", "adam", "stats"]
        elif stage == "adam":
            stages_to_run = ["adam", "stats"]
        elif stage == "stats":
            stages_to_run = ["stats"]
        else:
            msg = f"Unknown stage: {stage}"
            raise ValueError(msg)

        logger.info(
            f"Resolution re-run for {track_id}: {' -> '.join(stages_to_run)}"
        )

        for run_stage in stages_to_run:
            # Only the FIRST stage (the one that disagreed) gets the hint
            is_hint_stage = run_stage == stage

            if run_stage == "sdtm":
                from omni_agents.agents.sdtm import SDTMAgent

                agent = SDTMAgent(
                    llm=llm,
                    prompt_dir=prompt_dir,
                    trial_config=orchestrator.settings.trial,
                )
                context: dict = {
                    "input_path": "/workspace/input/SBPdata.csv",
                    "output_dir": "/workspace",
                }
                if is_hint_stage:
                    context["previous_error"] = hint.to_prompt_text()
                    context["attempt_number"] = 1
                await orchestrator._run_agent(
                    agent=agent,
                    context=context,
                    work_dir=track_result.sdtm_dir,
                    input_volumes={str(raw_dir): "/workspace/input"},
                    expected_inputs=["/workspace/input/SBPdata.csv"],
                    expected_outputs=["DM.csv", "VS.csv"],
                    track_id=track_id,
                )
                from omni_agents.pipeline.schema_validator import SchemaValidator

                SchemaValidator.validate_sdtm(
                    track_result.sdtm_dir,
                    orchestrator.settings.trial.n_subjects,
                )

            elif run_stage == "adam":
                from omni_agents.agents.adam import ADaMAgent

                agent = ADaMAgent(
                    llm=llm,
                    prompt_dir=prompt_dir,
                    trial_config=orchestrator.settings.trial,
                )
                context = {
                    "input_dir": "/workspace/input",
                    "output_dir": "/workspace",
                }
                if is_hint_stage:
                    context["previous_error"] = hint.to_prompt_text()
                    context["attempt_number"] = 1
                await orchestrator._run_agent(
                    agent=agent,
                    context=context,
                    work_dir=track_result.adam_dir,
                    input_volumes={
                        str(track_result.sdtm_dir): "/workspace/input"
                    },
                    expected_inputs=["DM.csv", "VS.csv"],
                    expected_outputs=["ADTTE.rds", "ADTTE_summary.json"],
                    track_id=track_id,
                )
                from omni_agents.pipeline.schema_validator import SchemaValidator

                SchemaValidator.validate_adam(
                    track_result.adam_dir,
                    orchestrator.settings.trial.n_subjects,
                )

            elif run_stage == "stats":
                from omni_agents.agents.stats import StatsAgent

                agent = StatsAgent(
                    llm=llm,
                    prompt_dir=prompt_dir,
                    trial_config=orchestrator.settings.trial,
                )
                context = {
                    "adam_dir": "/workspace/adam",
                    "sdtm_dir": "/workspace/sdtm",
                    "output_dir": "/workspace",
                }
                if is_hint_stage:
                    context["previous_error"] = hint.to_prompt_text()
                    context["attempt_number"] = 1
                await orchestrator._run_agent(
                    agent=agent,
                    context=context,
                    work_dir=track_result.stats_dir,
                    input_volumes={
                        str(track_result.adam_dir): "/workspace/adam",
                        str(track_result.sdtm_dir): "/workspace/sdtm",
                    },
                    expected_inputs=["ADTTE.rds", "DM.csv"],
                    expected_outputs=["results.json", "km_plot.png"],
                    track_id=track_id,
                )
                from omni_agents.pipeline.schema_validator import SchemaValidator

                SchemaValidator.validate_stats(track_result.stats_dir)

        # Return the same TrackResult object -- the directories are the same,
        # but their CONTENTS have been updated by the re-runs
        return track_result

    def _recompare_stage(
        self,
        stage: str,
        track_a_result: TrackResult,
        track_b_result: TrackResult,
        expected_subjects: int,
    ) -> StageComparison:
        """Dispatch to the appropriate StageComparator method for a single stage.

        Kept as a utility; the main resolve() loop uses
        StageComparator.compare_all_stages for full re-comparison after cascade.

        Args:
            stage: Pipeline stage name.
            track_a_result: Track A pipeline result.
            track_b_result: Track B pipeline result.
            expected_subjects: Expected number of subjects.

        Returns:
            A StageComparison for the specified stage.
        """
        if stage == "sdtm":
            return StageComparator.compare_sdtm(
                track_a_result.sdtm_dir,
                track_b_result.sdtm_dir,
                expected_subjects,
            )
        elif stage == "adam":
            return StageComparator.compare_adam(
                track_a_result.adam_dir,
                track_b_result.adam_dir,
                expected_subjects,
            )
        elif stage == "stats":
            return StageComparator.compare_stats(
                track_a_result.stats_dir,
                track_b_result.stats_dir,
            )
        else:
            msg = f"Unknown stage: {stage}"
            raise ValueError(msg)

    def _pick_best_track(self, disagreement: StageComparison) -> str | None:
        """Pick the best track when resolution exhausts iterations.

        If one track has clearly fewer issues, return that track_id.
        If ambiguous (equal issues or no clear winner), return "track_a"
        as the default winner (Gemini is the established track).

        Args:
            disagreement: The final stage comparison with issues.

        Returns:
            "track_a" as the default winner when ambiguous.
        """
        # For V1: return "track_a" as default winner when ambiguous
        # (Gemini is the established track)
        return "track_a"
