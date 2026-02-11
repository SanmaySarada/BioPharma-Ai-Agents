"""Stats agent (Agent 4A): produces survival analysis and demographics outputs.

Reads ADTTE.rds (from ADaM step) and DM.csv/VS.csv (from SDTM step)
to produce Table 1 (demographics), Table 2 (KM + log-rank), Table 3
(Cox HR), Figure 1 (KM plot), and results.json (structured output
for Track B comparison in Phase 3).
"""

from pathlib import Path

from omni_agents.agents.base import BaseAgent
from omni_agents.config import TrialConfig
from omni_agents.llm.base import BaseLLM, LLMResponse


class StatsAgent(BaseAgent):
    """Agent 4A: Statistical analysis of clinical trial data.

    Reads ADTTE.rds, DM.csv, and VS.csv to produce demographics
    summaries, survival analysis tables, a Kaplan-Meier plot, and
    structured JSON for downstream consensus comparison.
    """

    def __init__(
        self, llm: BaseLLM, prompt_dir: Path, trial_config: TrialConfig
    ) -> None:
        super().__init__(llm, prompt_dir)
        self.trial_config = trial_config

    @property
    def name(self) -> str:
        return "stats"

    @property
    def prompt_template_name(self) -> str:
        return "stats.j2"

    def get_system_prompt_vars(self) -> dict:
        """Extract template variables from trial config."""
        tc = self.trial_config
        return {
            "n_subjects": tc.n_subjects,
            "event_threshold": 120,
        }

    def build_user_prompt(self, context: dict) -> str:
        """Build user prompt for the Stats agent.

        For the initial call, instructs the LLM to read from adam and
        sdtm directories. For retries, includes error feedback.
        """
        adam_dir = context.get("adam_dir", "/workspace/adam")
        sdtm_dir = context.get("sdtm_dir", "/workspace/sdtm")
        output_dir = context.get("output_dir", "/workspace")

        if "previous_error" in context:
            return (
                f"Your previous R code produced an error. "
                f"This is attempt {context['attempt_number']}.\n\n"
                f"Error output:\n```\n{context['previous_error']}\n```\n\n"
                f"Fix the R code. Read ADTTE.rds from '{adam_dir}/ADTTE.rds', "
                f"DM.csv from '{sdtm_dir}/DM.csv', and VS.csv from '{sdtm_dir}/VS.csv'. "
                f"Write all outputs to '{output_dir}'."
            )

        return (
            f"Generate R code to perform survival analysis on clinical trial data. "
            f"Read ADTTE.rds from '{adam_dir}/ADTTE.rds', "
            f"DM.csv from '{sdtm_dir}/DM.csv', and VS.csv from '{sdtm_dir}/VS.csv'. "
            f"Write all outputs to '{output_dir}'."
        )

    async def generate_code(
        self,
        context: dict,
        system_prompt_vars: dict | None = None,
    ) -> tuple[str, LLMResponse]:
        """Override to inject trial config vars into system prompt."""
        vars_to_use = system_prompt_vars or self.get_system_prompt_vars()
        return await super().generate_code(context, vars_to_use)
