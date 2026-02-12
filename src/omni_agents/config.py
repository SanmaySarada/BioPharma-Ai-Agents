"""Pydantic settings models for all configuration."""

import os
from pathlib import Path

import yaml
from pydantic import BaseModel


class TrialConfig(BaseModel):
    """Clinical trial protocol parameters."""

    n_subjects: int = 300
    randomization_ratio: str = "2:1"
    seed: int = 12345
    visits: int = 26
    endpoint: str = "SBP"
    treatment_sbp_mean: float = 120.0
    treatment_sbp_sd: float = 10.0
    placebo_sbp_mean: float = 140.0
    placebo_sbp_sd: float = 20.0
    baseline_sbp_mean: float = 150.0
    baseline_sbp_sd: float = 10.0
    age_mean: float = 55.0
    age_sd: float = 10.0
    missing_rate: float = 0.03
    dropout_rate: float = 0.10


class DockerConfig(BaseModel):
    """Docker execution environment settings."""

    image: str = "omni-r-clinical:latest"
    memory_limit: str = "2g"
    cpu_count: int = 1
    timeout: int = 300
    network_disabled: bool = True


class GeminiConfig(BaseModel):
    """Google Gemini API configuration."""

    api_key: str
    model: str = "gemini-2.5-pro"
    temperature: float = 0.0


class OpenAIConfig(BaseModel):
    """OpenAI GPT-4 API configuration."""

    api_key: str
    model: str = "gpt-4o"
    temperature: float = 0.0


class LLMConfig(BaseModel):
    """LLM provider configuration for both tracks."""

    gemini: GeminiConfig
    openai: OpenAIConfig


class ResolutionConfig(BaseModel):
    """Configuration for the adversarial resolution loop.

    Controls whether the resolution loop activates when stage comparison
    detects disagreements between tracks, and the maximum number of
    resolution iterations to attempt.

    Attributes:
        enabled: Whether to attempt resolution on disagreement.
        max_iterations: Maximum resolution retry iterations.
    """

    enabled: bool = True
    max_iterations: int = 2


class Settings(BaseModel):
    """Root configuration model for the omni-agents pipeline."""

    trial: TrialConfig = TrialConfig()
    docker: DockerConfig = DockerConfig()
    llm: LLMConfig
    resolution: ResolutionConfig = ResolutionConfig()
    output_dir: str = "./output"

    @classmethod
    def from_yaml(cls, path: Path) -> "Settings":
        """Load and validate settings from a YAML configuration file.

        Environment variable substitution is supported for API keys and other
        sensitive values: if a YAML value starts with ``$``, the corresponding
        environment variable is resolved at load time.

        Args:
            path: Path to the YAML configuration file.

        Returns:
            Validated Settings instance.

        Raises:
            FileNotFoundError: If the YAML file does not exist.
            ValueError: If a referenced environment variable is not set.
        """
        raw = yaml.safe_load(path.read_text())
        resolved = _resolve_env_vars(raw)
        return cls.model_validate(resolved)


def _resolve_env_vars(data: object) -> object:
    """Recursively resolve environment variable references in config data.

    Any string value starting with ``$`` is treated as an environment variable
    reference and replaced with the value of that variable.

    Args:
        data: Configuration data (dict, list, or scalar).

    Returns:
        Data with environment variable references resolved.

    Raises:
        ValueError: If a referenced environment variable is not set.
    """
    if isinstance(data, dict):
        return {k: _resolve_env_vars(v) for k, v in data.items()}
    if isinstance(data, list):
        return [_resolve_env_vars(item) for item in data]
    if isinstance(data, str) and data.startswith("$"):
        var_name = data[1:]
        value = os.environ.get(var_name)
        if value is None:
            msg = (
                f"Environment variable '{var_name}' is not set "
                f"(referenced as '{data}' in config)"
            )
            raise ValueError(msg)
        return value
    return data
