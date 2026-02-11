"""Simulator agent (Agent 1): generates synthetic SBP clinical trial data.

Calls Gemini to produce R code that creates a CSV file with N subjects,
longitudinal visit structure, treatment arms, demographics, and missingness
patterns.
"""

from pathlib import Path

from omni_agents.agents.base import BaseAgent
from omni_agents.config import TrialConfig
from omni_agents.llm.base import BaseLLM, LLMResponse


class SimulatorAgent(BaseAgent):
    """Agent 1: Generates synthetic SBP clinical trial data.

    Calls Gemini to produce R code that creates a CSV file with
    N subjects, longitudinal visit structure, treatment arms,
    demographics, and missingness patterns.
    """

    def __init__(
        self, llm: BaseLLM, prompt_dir: Path, trial_config: TrialConfig
    ) -> None:
        super().__init__(llm, prompt_dir)
        self.trial_config = trial_config

    @property
    def name(self) -> str:
        return "simulator"

    @property
    def prompt_template_name(self) -> str:
        return "simulator.j2"

    def get_system_prompt_vars(self) -> dict:
        """Extract template variables from trial config."""
        tc = self.trial_config
        return {
            "n_subjects": tc.n_subjects,
            "randomization_ratio": tc.randomization_ratio,
            "visits": tc.visits,
            "baseline_sbp_mean": tc.baseline_sbp_mean,
            "baseline_sbp_sd": tc.baseline_sbp_sd,
            "treatment_sbp_mean": tc.treatment_sbp_mean,
            "treatment_sbp_sd": tc.treatment_sbp_sd,
            "placebo_sbp_mean": tc.placebo_sbp_mean,
            "placebo_sbp_sd": tc.placebo_sbp_sd,
            "age_mean": tc.age_mean,
            "age_sd": tc.age_sd,
            "missing_rate": tc.missing_rate,
            "dropout_rate": tc.dropout_rate,
        }

    def build_user_prompt(self, context: dict) -> str:
        """Build user prompt for the Simulator.

        For the initial call, the user prompt is straightforward.
        For retries, it includes the error feedback.
        """
        output_path = context.get("output_path", "/workspace/SBPdata.csv")

        if "previous_error" in context:
            return (
                f"Your previous R code produced an error. "
                f"This is attempt {context['attempt_number']}.\n\n"
                f"Error output:\n```\n{context['previous_error']}\n```\n\n"
                f"Please fix the R code and try again. "
                f"Write the corrected R code that generates the synthetic trial data "
                f"and saves it to '{output_path}'."
            )

        return (
            f"Generate R code to create synthetic SBP clinical trial data. "
            f"Save the output as a CSV file to '{output_path}'. "
            f"The data must follow the exact specifications in the system prompt."
        )

    async def generate_code(
        self,
        context: dict,
        system_prompt_vars: dict | None = None,
    ) -> tuple[str, LLMResponse]:
        """Override to inject trial config vars into system prompt."""
        vars_to_use = system_prompt_vars or self.get_system_prompt_vars()
        return await super().generate_code(context, vars_to_use)
