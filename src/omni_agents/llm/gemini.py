"""Google Gemini async LLM adapter using the google-genai SDK."""

from typing import TypeVar

from google import genai
from google.genai import types
from pydantic import BaseModel

from omni_agents.config import GeminiConfig
from omni_agents.llm.base import BaseLLM, LLMError, LLMResponse

_T = TypeVar("_T", bound=BaseModel)


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

    async def generate_structured(
        self,
        system_prompt: str,
        user_prompt: str,
        response_model: type[_T],
    ) -> _T:
        """Generate structured output using Gemini's response_schema.

        Uses ``response_mime_type='application/json'`` with ``response_schema``
        set to the Pydantic model.  Falls back to manual JSON parsing via
        :func:`extract_json` if the SDK's built-in parsing is unavailable.

        Args:
            system_prompt: System instruction for the model.
            user_prompt: User message / task description.
            response_model: Pydantic model class for structured output.

        Returns:
            An instance of *response_model* populated by the LLM.

        Raises:
            LLMError: If the Gemini API call or parsing fails.
        """
        try:
            response = await self.client.aio.models.generate_content(
                model=self.model,
                contents=user_prompt,
                config=types.GenerateContentConfig(
                    system_instruction=system_prompt,
                    temperature=self.temperature,
                    response_mime_type="application/json",
                    response_schema=response_model,
                ),
            )
        except Exception as exc:
            raise LLMError(
                provider="gemini",
                message=f"Structured generation failed: {exc}",
                original_error=exc,
            ) from exc

        # Try SDK's built-in parsing first.
        if hasattr(response, "parsed") and response.parsed is not None:
            return response.parsed  # type: ignore[return-value]

        # Fallback: parse JSON from response text manually.
        from omni_agents.llm.response_parser import extract_json

        raw_text = response.text or ""
        data = extract_json(raw_text)
        if data is None:
            raise LLMError(
                provider="gemini",
                message=f"Could not parse structured output from response: {raw_text[:200]}",
            )
        return response_model.model_validate(data)
