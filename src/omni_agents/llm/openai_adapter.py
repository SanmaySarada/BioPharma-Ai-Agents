"""OpenAI GPT-4 async LLM adapter using the official openai SDK."""

from typing import TypeVar

from openai import APIError, AsyncOpenAI
from pydantic import BaseModel

from omni_agents.config import OpenAIConfig
from omni_agents.llm.base import BaseLLM, LLMError, LLMResponse

_T = TypeVar("_T", bound=BaseModel)


class OpenAIAdapter(BaseLLM):
    """Async adapter for the OpenAI Chat Completions API.

    Uses ``AsyncOpenAI`` for native async support with ``asyncio``.

    Args:
        config: OpenAI-specific configuration (API key, model, temperature).
    """

    def __init__(self, config: OpenAIConfig) -> None:
        self.client = AsyncOpenAI(api_key=config.api_key)
        self.model = config.model
        self.temperature = config.temperature

    @property
    def provider(self) -> str:  # noqa: D401
        """The provider identifier."""
        return "openai"

    async def generate(self, system_prompt: str, user_prompt: str) -> LLMResponse:
        """Generate a response from the OpenAI Chat Completions API.

        Args:
            system_prompt: System message for the model.
            user_prompt: User message / task description.

        Returns:
            ``LLMResponse`` with the raw text and token usage metadata.

        Raises:
            LLMError: If the OpenAI API call fails.
        """
        try:
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=self.temperature,
            )
        except APIError as exc:
            raise LLMError(
                provider="openai",
                message=str(exc),
                original_error=exc,
            ) from exc

        # Extract token counts when available.
        input_tokens: int | None = None
        output_tokens: int | None = None
        if response.usage:
            input_tokens = response.usage.prompt_tokens
            output_tokens = response.usage.completion_tokens

        raw_text = ""
        if response.choices and response.choices[0].message.content:
            raw_text = response.choices[0].message.content

        return LLMResponse(
            raw_text=raw_text,
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
        """Generate structured output using OpenAI's beta parse API.

        Uses ``client.beta.chat.completions.parse()`` with ``response_format``
        set to the Pydantic model.  Falls back to manual JSON parsing via
        :func:`extract_json` if SDK parsing returns ``None``.

        Args:
            system_prompt: System message for the model.
            user_prompt: User message / task description.
            response_model: Pydantic model class for structured output.

        Returns:
            An instance of *response_model* populated by the LLM.

        Raises:
            LLMError: If the OpenAI API call or parsing fails.
        """
        try:
            completion = await self.client.beta.chat.completions.parse(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=self.temperature,
                response_format=response_model,
            )
        except APIError as exc:
            raise LLMError(
                provider="openai",
                message=f"Structured generation failed: {exc}",
                original_error=exc,
            ) from exc

        parsed = completion.choices[0].message.parsed
        if parsed is None:
            # Fallback: try manual JSON parsing from content.
            from omni_agents.llm.response_parser import extract_json

            raw_text = completion.choices[0].message.content or ""
            data = extract_json(raw_text)
            if data is None:
                raise LLMError(
                    provider="openai",
                    message="Structured output parsing returned None",
                )
            return response_model.model_validate(data)

        return parsed  # type: ignore[return-value]
