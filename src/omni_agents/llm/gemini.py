"""Google Gemini async LLM adapter using the google-genai SDK."""

from google import genai
from google.genai import types

from omni_agents.config import GeminiConfig
from omni_agents.llm.base import BaseLLM, LLMError, LLMResponse


class GeminiAdapter(BaseLLM):
    """Async adapter for the Google Gemini API.

    Uses the ``google-genai`` SDK (not the deprecated ``google-generativeai``
    package).  Async calls are made via ``client.aio``.

    Args:
        config: Gemini-specific configuration (API key, model, temperature).
    """

    def __init__(self, config: GeminiConfig) -> None:
        self.client = genai.Client(api_key=config.api_key)
        self.model = config.model
        self.temperature = config.temperature

    @property
    def provider(self) -> str:  # noqa: D401
        """The provider identifier."""
        return "gemini"

    async def generate(self, system_prompt: str, user_prompt: str) -> LLMResponse:
        """Generate a response from the Gemini API.

        Args:
            system_prompt: System instruction for the model.
            user_prompt: User message / task description.

        Returns:
            ``LLMResponse`` with the raw text and token usage metadata.

        Raises:
            LLMError: If the Gemini API call fails.
        """
        try:
            response = await self.client.aio.models.generate_content(
                model=self.model,
                contents=user_prompt,
                config=types.GenerateContentConfig(
                    system_instruction=system_prompt,
                    temperature=self.temperature,
                ),
            )
        except Exception as exc:
            raise LLMError(
                provider="gemini",
                message=str(exc),
                original_error=exc,
            ) from exc

        # Extract token counts when available.
        input_tokens: int | None = None
        output_tokens: int | None = None
        if response.usage_metadata:
            input_tokens = getattr(response.usage_metadata, "prompt_token_count", None)
            output_tokens = getattr(response.usage_metadata, "candidates_token_count", None)

        return LLMResponse(
            raw_text=response.text or "",
            model=self.model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
        )
