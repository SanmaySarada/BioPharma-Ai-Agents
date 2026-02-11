"""Medical Writer agent (Agent 6): generates Clinical Study Report as Word document.

Reads Track A stats output (results.json, table CSVs, km_plot.png) and
consensus verdict (verdict.json) to produce a Word document (.docx) CSR
using R officer + flextable packages.
"""

from pathlib import Path

from omni_agents.agents.base import BaseAgent
from omni_agents.config import TrialConfig
from omni_agents.llm.base import BaseLLM, LLMResponse


class MedicalWriterAgent(BaseAgent):
    """Agent 6: Medical Writer generating Clinical Study Report.

    Reads results.json, verdict.json, table CSVs, and km_plot.png
    to produce a Word document CSR with embedded tables, figures,
    cross-referenced statistics, and data dictionary.
    """

    def __init__(
        self, llm: BaseLLM, prompt_dir: Path, trial_config: TrialConfig
    ) -> None:
        super().__init__(llm, prompt_dir)
        self.trial_config = trial_config

    @property
    def name(self) -> str:
        return "medical_writer"

    @property
    def prompt_template_name(self) -> str:
        return "medical_writer.j2"

    def get_system_prompt_vars(self) -> dict:
        """Extract template variables from trial config."""
        tc = self.trial_config
        return {
            "n_subjects": tc.n_subjects,
            "event_threshold": 120,
        }

    def build_user_prompt(self, context: dict) -> str:
        """Build user prompt for the Medical Writer agent.

        Context keys:
          - results_path: path to results.json inside container
          - verdict_path: path to verdict.json inside container
          - table1_path, table2_path, table3_path: paths to table CSVs
          - km_plot_path: path to km_plot.png
          - output_dir: where to write clinical_study_report.docx
        """
        results_path = context.get("results_path", "/workspace/stats/results.json")
        verdict_path = context.get("verdict_path", "/workspace/consensus/verdict.json")
        table1_path = context.get(
            "table1_path", "/workspace/stats/table1_demographics.csv"
        )
        table2_path = context.get(
            "table2_path", "/workspace/stats/table2_km_results.csv"
        )
        table3_path = context.get(
            "table3_path", "/workspace/stats/table3_cox_results.csv"
        )
        km_plot_path = context.get("km_plot_path", "/workspace/stats/km_plot.png")
        output_dir = context.get("output_dir", "/workspace")

        if "previous_error" in context:
            return (
                f"Your previous R code produced an error. "
                f"This is attempt {context['attempt_number']}.\n\n"
                f"Error output:\n```\n{context['previous_error']}\n```\n\n"
                f"Fix the R code. Read inputs from:\n"
                f"- results.json: '{results_path}'\n"
                f"- verdict.json: '{verdict_path}'\n"
                f"- table1_demographics.csv: '{table1_path}'\n"
                f"- table2_km_results.csv: '{table2_path}'\n"
                f"- table3_cox_results.csv: '{table3_path}'\n"
                f"- km_plot.png: '{km_plot_path}'\n\n"
                f"Write the CSR document to '{output_dir}/clinical_study_report.docx'."
            )

        return (
            f"Generate R code to produce a Clinical Study Report as a Word document. "
            f"Read inputs from:\n"
            f"- results.json: '{results_path}'\n"
            f"- verdict.json: '{verdict_path}'\n"
            f"- table1_demographics.csv: '{table1_path}'\n"
            f"- table2_km_results.csv: '{table2_path}'\n"
            f"- table3_cox_results.csv: '{table3_path}'\n"
            f"- km_plot.png: '{km_plot_path}'\n\n"
            f"Write the CSR document to '{output_dir}/clinical_study_report.docx'."
        )

    async def generate_code(
        self,
        context: dict,
        system_prompt_vars: dict | None = None,
    ) -> tuple[str, LLMResponse]:
        """Override to inject trial config vars into system prompt."""
        vars_to_use = system_prompt_vars or self.get_system_prompt_vars()
        return await super().generate_code(context, vars_to_use)
