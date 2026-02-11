"""Abstract base agent class with prompt construction and code generation.

All pipeline agents inherit from ``BaseAgent``.  An agent is a stateless
worker: it receives context, calls an LLM, and returns generated R code.
The orchestrator owns execution, retry, and state management.
"""

import re
from abc import ABC, abstractmethod
from pathlib import Path

from jinja2 import Template

from omni_agents.llm.base import BaseLLM, LLMResponse
from omni_agents.llm.response_parser import extract_r_code


class BaseAgent(ABC):
    """Base class for all pipeline agents.

    Agents are stateless workers: they receive context, call an LLM,
    and return generated R code. The orchestrator owns execution, retry,
    and state management.
    """

    def __init__(self, llm: BaseLLM, prompt_dir: Path) -> None:
        self.llm = llm
        self.prompt_dir = prompt_dir

    @property
    @abstractmethod
    def name(self) -> str:
        """Agent name for logging and identification."""
        ...

    @property
    @abstractmethod
    def prompt_template_name(self) -> str:
        """Filename of the Jinja2 prompt template (e.g., 'simulator.j2')."""
        ...

    @abstractmethod
    def build_user_prompt(self, context: dict) -> str:
        """Build the user prompt from pipeline context.

        Args:
            context: Dict containing workspace paths, prior results,
                     and optionally previous_error for retries.
        """
        ...

    def load_system_prompt(self, **template_vars: object) -> str:
        """Load and render the system prompt from a Jinja2 template file."""
        template_path = self.prompt_dir / self.prompt_template_name
        template_text = template_path.read_text()
        template = Template(template_text)
        return template.render(**template_vars)

    async def generate_code(
        self,
        context: dict,
        system_prompt_vars: dict | None = None,
    ) -> tuple[str, LLMResponse]:
        """Generate R code by calling the LLM.

        Returns:
            Tuple of (r_code, raw_llm_response).

        Raises:
            ValueError: If the LLM response contains no extractable R code.
        """
        system_prompt = self.load_system_prompt(**(system_prompt_vars or {}))
        user_prompt = self.build_user_prompt(context)
        response = await self.llm.generate(system_prompt, user_prompt)
        code = extract_r_code(response.raw_text)
        if code is None:
            msg = f"Agent {self.name}: LLM response contained no extractable R code"
            raise ValueError(msg)
        return code, response

    def inject_seed(self, code: str, seed: int) -> str:
        """Inject ``set.seed()`` at the top of R code for reproducibility.

        The orchestrator calls this -- we do NOT rely on the LLM
        to include ``set.seed()`` (Pitfall 5).
        """
        seed_line = f"set.seed({seed})\n\n"
        # If the code already has set.seed, replace it with ours
        code = re.sub(r"set\.seed\(\d+\)\s*\n?", "", code)
        return seed_line + code

    def make_retry_context(
        self, context: dict, previous_error: str, attempt: int
    ) -> dict:
        """Create a context dict for retry attempts with error feedback."""
        retry_context = context.copy()
        retry_context["previous_error"] = previous_error
        retry_context["attempt_number"] = attempt
        return retry_context
