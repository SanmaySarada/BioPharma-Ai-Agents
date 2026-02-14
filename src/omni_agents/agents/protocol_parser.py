"""Protocol parser agent: extracts trial config from .docx documents.

NOT a BaseAgent subclass -- this agent produces structured data (TrialConfig),
not R code.  It runs in-process (no Docker) and is invoked before the pipeline.
"""

from pathlib import Path

from jinja2 import Template

from omni_agents.agents.docx_reader import extract_protocol_text
from omni_agents.config import (
    ExtractionResult,
    ProtocolExtraction,
    TrialConfig,
    merge_extraction,
)
from omni_agents.llm.base import BaseLLM


class ProtocolParserAgent:
    """Parses a clinical trial protocol document into a TrialConfig.

    Workflow:

    1. Read ``.docx`` with python-docx (paragraphs + tables).
    2. Load system prompt from ``protocol_parser.j2``.
    3. Call LLM with structured output (:class:`ProtocolExtraction` schema).
    4. Merge extraction with :class:`TrialConfig` defaults.
    5. Return :class:`ExtractionResult` with field tracking.

    Args:
        llm: Any :class:`BaseLLM` adapter (Gemini recommended for
            single-shot extraction).
        prompt_dir: Directory containing prompt templates.
    """

    TEMPLATE_NAME = "protocol_parser.j2"

    def __init__(self, llm: BaseLLM, prompt_dir: Path) -> None:
        self.llm = llm
        self.prompt_dir = prompt_dir

    async def parse(
        self,
        protocol_path: Path,
        defaults: TrialConfig | None = None,
    ) -> ExtractionResult:
        """Extract trial parameters from a .docx protocol document.

        Args:
            protocol_path: Path to the .docx protocol file.
            defaults: Optional custom TrialConfig defaults.  Uses
                ``TrialConfig()`` if not provided.

        Returns:
            :class:`ExtractionResult` with merged config and field tracking.

        Raises:
            FileNotFoundError: If protocol_path does not exist.
            LLMError: If the LLM call fails.
            ValidationError: If extracted values fail Pydantic validation.
        """
        # 1. Extract document text
        document_text = extract_protocol_text(protocol_path)

        # 2. Load and render system prompt
        template_path = self.prompt_dir / self.TEMPLATE_NAME
        template_text = template_path.read_text()
        template = Template(template_text)

        # Pass TrialConfig field info to template for schema description
        field_info = self._build_field_info()
        system_prompt = template.render(fields=field_info)

        # 3. Call LLM with structured output
        extraction = await self.llm.generate_structured(
            system_prompt=system_prompt,
            user_prompt=document_text,
            response_model=ProtocolExtraction,
        )

        # 4. Merge with defaults
        return merge_extraction(extraction, defaults)

    @staticmethod
    def _build_field_info() -> list[dict[str, str]]:
        """Build field descriptions for the prompt template.

        Returns a list of dicts with name, type, description, synonyms,
        and range for each TrialConfig field the LLM should extract.
        """
        return [
            {
                "name": "n_subjects",
                "type": "integer",
                "description": "Total number of subjects enrolled in the trial",
                "synonyms": "sample size, enrolled, participants, subjects, N",
                "range": "10 to 10000",
            },
            {
                "name": "randomization_ratio",
                "type": "string",
                "description": "Treatment-to-placebo randomization ratio",
                "synonyms": "randomization, allocation ratio",
                "range": "format like '2:1' or '1:1'",
            },
            {
                "name": "visits",
                "type": "integer",
                "description": "Number of study visits (including baseline)",
                "synonyms": "visits, assessments, measurement timepoints",
                "range": "2 to 100",
            },
            {
                "name": "endpoint",
                "type": "string",
                "description": "Primary efficacy endpoint abbreviation",
                "synonyms": "primary endpoint, primary outcome, efficacy measure",
                "range": "short abbreviation like 'SBP', 'DBP', 'HbA1c'",
            },
            {
                "name": "treatment_sbp_mean",
                "type": "float",
                "description": "Expected mean SBP in the treatment arm at end of study",
                "synonyms": "target SBP, treatment arm mean, active treatment blood pressure",
                "range": "50.0 to 250.0 mmHg",
            },
            {
                "name": "treatment_sbp_sd",
                "type": "float",
                "description": "Standard deviation of SBP in the treatment arm",
                "synonyms": "treatment SD, treatment variability",
                "range": "1.0 to 50.0 mmHg",
            },
            {
                "name": "placebo_sbp_mean",
                "type": "float",
                "description": "Expected mean SBP in the placebo arm at end of study",
                "synonyms": "placebo mean, control arm blood pressure",
                "range": "50.0 to 250.0 mmHg",
            },
            {
                "name": "placebo_sbp_sd",
                "type": "float",
                "description": "Standard deviation of SBP in the placebo arm",
                "synonyms": "placebo SD, control variability",
                "range": "1.0 to 50.0 mmHg",
            },
            {
                "name": "baseline_sbp_mean",
                "type": "float",
                "description": "Mean baseline SBP across all subjects at enrollment",
                "synonyms": "baseline blood pressure, enrollment SBP, screening SBP",
                "range": "50.0 to 250.0 mmHg",
            },
            {
                "name": "baseline_sbp_sd",
                "type": "float",
                "description": "Standard deviation of baseline SBP",
                "synonyms": "baseline variability, baseline SD",
                "range": "1.0 to 50.0 mmHg",
            },
            {
                "name": "age_mean",
                "type": "float",
                "description": "Mean age of study population",
                "synonyms": "average age, mean participant age",
                "range": "18.0 to 100.0 years",
            },
            {
                "name": "age_sd",
                "type": "float",
                "description": "Standard deviation of age in study population",
                "synonyms": "age variability, age SD",
                "range": "1.0 to 30.0 years",
            },
            {
                "name": "missing_rate",
                "type": "float",
                "description": (
                    "Expected rate of missing data (as decimal fraction 0.0-1.0)"
                ),
                "synonyms": "missing data rate, data completeness gap",
                "range": (
                    "0.0 to 1.0 (MUST be decimal fraction, NOT percentage. "
                    "If protocol says '3%', extract 0.03)"
                ),
            },
            {
                "name": "dropout_rate",
                "type": "float",
                "description": (
                    "Expected dropout/discontinuation rate "
                    "(as decimal fraction 0.0-1.0)"
                ),
                "synonyms": "dropout, discontinuation rate, withdrawal rate, attrition",
                "range": (
                    "0.0 to 1.0 (MUST be decimal fraction, NOT percentage. "
                    "If protocol says '10%', extract 0.10)"
                ),
            },
        ]
