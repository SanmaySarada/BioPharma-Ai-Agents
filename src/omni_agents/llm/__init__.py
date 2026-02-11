"""LLM provider adapters for Gemini and OpenAI."""

from omni_agents.llm.base import BaseLLM, LLMError, LLMResponse
from omni_agents.llm.response_parser import extract_r_code

__all__ = [
    "BaseLLM",
    "LLMError",
    "LLMResponse",
    "extract_r_code",
]
