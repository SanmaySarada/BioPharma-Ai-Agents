"""ADaM Engineer agent (Agent 3A): constructs ADTTE from SDTM domains.

Calls Gemini to produce R code that reads DM.csv and VS.csv, then creates
ADTTE.rds (for R consumption by Stats agent) and ADTTE_summary.json (for
Python-side validation by SchemaValidator).
"""

from pathlib import Path

from omni_agents.agents.base import BaseAgent
from omni_agents.config import TrialConfig
from omni_agents.llm.base import BaseLLM, LLMResponse


class ADaMAgent(BaseAgent):
    """Agent 3A: Constructs ADTTE (time-to-event) dataset from SDTM domains.

    Reads DM.csv and VS.csv produced by the Simulator/SDTM step and
    generates R code that creates ADTTE.rds plus ADTTE_summary.json.
    The critical challenge is CNSR convention (0=event) and NA handling.
    """

    def __init__(
        self, llm: BaseLLM, prompt_dir: Path, trial_config: TrialConfig
    ) -> None:
        super().__init__(llm, prompt_dir)
        self.trial_config = trial_config

    @property
    def name(self) -> str:
        return "adam"

    @property
    def prompt_template_name(self) -> str:
        return "adam.j2"

    def get_system_prompt_vars(self) -> dict:
        """Extract template variables from trial config."""
        tc = self.trial_config
        return {
            "n_subjects": tc.n_subjects,
            "visits": tc.visits,
            "study_id": "SBP-001",
            "event_threshold": 120,  # SBP < 120 = event
        }

    def build_user_prompt(self, context: dict) -> str:
        """Build user prompt for the ADaM agent.

        For the initial call, instructs R code generation for ADTTE.
        For retries, includes the error feedback.
        """
        input_dir = context.get("input_dir", "/workspace/input")
        output_dir = context.get("output_dir", "/workspace")

        if "previous_error" in context:
            return (
                f"Your previous R code produced an error. "
                f"This is attempt {context['attempt_number']}.\n\n"
                f"Error output:\n```\n{context['previous_error']}\n```\n\n"
                f"Fix the R code. Read DM.csv from '{input_dir}/DM.csv' and "
                f"VS.csv from '{input_dir}/VS.csv'. "
                f"Write ADTTE.rds to '{output_dir}/ADTTE.rds' and "
                f"ADTTE_summary.json to '{output_dir}/ADTTE_summary.json'."
            )

        return (
            f"Generate R code to construct an ADTTE (time-to-event) dataset "
            f"from CDISC SDTM domains. "
            f"Read DM.csv from '{input_dir}/DM.csv' and VS.csv from '{input_dir}/VS.csv'. "
            f"Write ADTTE.rds to '{output_dir}/ADTTE.rds' and "
            f"ADTTE_summary.json to '{output_dir}/ADTTE_summary.json'."
        )

    async def generate_code(
        self,
        context: dict,
        system_prompt_vars: dict | None = None,
    ) -> tuple[str, LLMResponse]:
        """Override to inject trial config vars into system prompt."""
        vars_to_use = system_prompt_vars or self.get_system_prompt_vars()
        return await super().generate_code(context, vars_to_use)
