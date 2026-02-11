"""Double Programmer agent (Agent 2B): independent statistical validation via GPT-4.

Reads ONLY raw SBPdata.csv (not SDTM, ADaM, or Track A outputs).
Produces validation.json with independently calculated statistics
and structural metadata for consensus comparison.
"""

from pathlib import Path

from omni_agents.agents.base import BaseAgent
from omni_agents.config import TrialConfig
from omni_agents.llm.base import BaseLLM, LLMResponse


class DoubleProgrammerAgent(BaseAgent):
    """Agent 2B: Independent statistical validation via GPT-4.

    Reads ONLY raw SBPdata.csv (not SDTM, ADaM, or Track A outputs).
    Produces validation.json with independently calculated statistics
    and structural metadata.
    """

    def __init__(
        self, llm: BaseLLM, prompt_dir: Path, trial_config: TrialConfig
    ) -> None:
        super().__init__(llm, prompt_dir)
        self.trial_config = trial_config

    @property
    def name(self) -> str:
        return "double_programmer"

    @property
    def prompt_template_name(self) -> str:
        return "double_programmer.j2"

    def get_system_prompt_vars(self) -> dict:
        """Extract template variables from trial config."""
        tc = self.trial_config
        return {
            "n_subjects": tc.n_subjects,
            "event_threshold": 120,
        }

    def build_user_prompt(self, context: dict) -> str:
        """Build user prompt for the Double Programmer agent.

        For the initial call, instructs the LLM to read raw data and
        produce validation JSON. For retries, includes error feedback.
        """
        input_path = context.get("input_path", "/workspace/input/SBPdata.csv")
        output_dir = context.get("output_dir", "/workspace")

        if "previous_error" in context:
            return (
                f"Your previous R code produced an error. "
                f"This is attempt {context['attempt_number']}.\n\n"
                f"Error output:\n```\n{context['previous_error']}\n```\n\n"
                f"Fix the R code. Read raw data from '{input_path}'. "
                f"Write validation.json to '{output_dir}/validation.json'."
            )

        return (
            f"Generate R code to independently validate clinical trial "
            f"survival analysis results from raw data. "
            f"Read the raw clinical trial CSV from '{input_path}'. "
            f"Write the validation JSON to '{output_dir}/validation.json'."
        )

    async def generate_code(
        self,
        context: dict,
        system_prompt_vars: dict | None = None,
    ) -> tuple[str, LLMResponse]:
        """Override to inject trial config vars into system prompt."""
        vars_to_use = system_prompt_vars or self.get_system_prompt_vars()
        return await super().generate_code(context, vars_to_use)
