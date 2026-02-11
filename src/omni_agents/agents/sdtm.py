"""SDTM Architect agent (Agent 2A): maps raw Simulator output to CDISC SDTM.

Takes the raw SBPdata.csv from the Simulator and produces DM.csv
(demographics, one row per subject) and VS.csv (vital signs, one row
per subject per visit) with CDISC-compliant column names, controlled
terminology, and data types.
"""

from pathlib import Path

from omni_agents.agents.base import BaseAgent
from omni_agents.config import TrialConfig
from omni_agents.llm.base import BaseLLM, LLMResponse


class SDTMAgent(BaseAgent):
    """Agent 2A: Maps raw clinical trial data to CDISC SDTM DM and VS domains.

    Takes raw SBPdata.csv and produces DM.csv (demographics) and VS.csv
    (vital signs) with CDISC-compliant column names, controlled terminology,
    and data types.
    """

    def __init__(
        self, llm: BaseLLM, prompt_dir: Path, trial_config: TrialConfig
    ) -> None:
        super().__init__(llm, prompt_dir)
        self.trial_config = trial_config

    @property
    def name(self) -> str:
        return "sdtm"

    @property
    def prompt_template_name(self) -> str:
        return "sdtm.j2"

    def get_system_prompt_vars(self) -> dict:
        """Extract template variables for SDTM prompt."""
        tc = self.trial_config
        return {
            "n_subjects": tc.n_subjects,
            "visits": tc.visits,
            "study_id": "SBP-001",
        }

    def build_user_prompt(self, context: dict) -> str:
        """Build user prompt for the SDTM Architect.

        For the initial call, the user prompt specifies input/output paths.
        For retries, it includes the error feedback.
        """
        input_path = context.get("input_path", "/workspace/input/SBPdata.csv")
        output_dir = context.get("output_dir", "/workspace")

        if "previous_error" in context:
            return (
                f"Your previous R code produced an error. "
                f"This is attempt {context['attempt_number']}.\n\n"
                f"Error output:\n```\n{context['previous_error']}\n```\n\n"
                f"Fix the R code. Read raw data from '{input_path}'. "
                f"Write DM.csv to '{output_dir}/DM.csv' and VS.csv to '{output_dir}/VS.csv'."
            )

        return (
            f"Generate R code to map raw clinical trial data to CDISC SDTM domains. "
            f"Read raw data from '{input_path}'. "
            f"Write DM.csv to '{output_dir}/DM.csv' and VS.csv to '{output_dir}/VS.csv'."
        )

    async def generate_code(
        self,
        context: dict,
        system_prompt_vars: dict | None = None,
    ) -> tuple[str, LLMResponse]:
        """Override to inject trial config vars into system prompt."""
        vars_to_use = system_prompt_vars or self.get_system_prompt_vars()
        return await super().generate_code(context, vars_to_use)
