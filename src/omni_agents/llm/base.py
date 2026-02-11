"""Abstract LLM adapter interface and shared types."""

from abc import ABC, abstractmethod
from pathlib import Path

from jinja2 import Template
from pydantic import BaseModel


class LLMResponse(BaseModel):
    """Raw LLM response before R code extraction."""

    raw_text: str
    model: str
    input_tokens: int | None = None
    output_tokens: int | None = None


class LLMError(Exception):
    """Error raised by LLM adapters on API failures.

    Attributes:
        provider: The LLM provider that raised the error ("gemini" or "openai").
        message: Human-readable error description.
        original_error: The underlying exception from the provider SDK, if any.
    """

    def __init__(
        self,
        provider: str,
        message: str,
        original_error: Exception | None = None,
    ) -> None:
        self.provider = provider
        self.message = message
        self.original_error = original_error
        super().__init__(f"[{provider}] {message}")


class BaseLLM(ABC):
    """Abstract base class for LLM provider adapters.

    All concrete adapters (Gemini, OpenAI) must implement ``provider`` and
    ``generate``.  The ``load_prompt_template`` helper is concrete and shared
    across providers -- it reads a Jinja2 template file from disk and renders
    it with the supplied keyword arguments.
    """

    @property
    @abstractmethod
    def provider(self) -> str:
        """Return the provider identifier (e.g. ``"gemini"`` or ``"openai"``)."""

    @abstractmethod
    async def generate(self, system_prompt: str, user_prompt: str) -> LLMResponse:
        """Send a prompt to the LLM and return the raw response.

        Args:
            system_prompt: The system-level instruction for the LLM.
            user_prompt: The user-level message / task description.

        Returns:
            An ``LLMResponse`` containing the raw text and token counts.

        Raises:
            LLMError: If the underlying API call fails.
        """

    def load_prompt_template(self, template_path: Path, **kwargs: object) -> str:
        """Load a Jinja2 template from *template_path* and render it.

        Args:
            template_path: Absolute or relative path to a ``.j2`` / ``.txt``
                template file.
            **kwargs: Variables to inject into the template.

        Returns:
            The rendered template string.

        Raises:
            FileNotFoundError: If *template_path* does not exist.
        """
        template_text = template_path.read_text()
        template = Template(template_text)
        return template.render(**kwargs)
