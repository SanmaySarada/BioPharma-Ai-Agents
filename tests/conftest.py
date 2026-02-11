"""Shared pytest fixtures for omni-ai-agents test suite."""

from pathlib import Path

import pytest


@pytest.fixture
def workspace_dir(tmp_path: Path) -> Path:
    """Create a temporary workspace directory structure for tests."""
    raw_dir = tmp_path / "raw"
    raw_dir.mkdir()
    track_a = tmp_path / "track_a"
    track_a.mkdir()
    track_b = tmp_path / "track_b"
    track_b.mkdir()
    consensus = tmp_path / "consensus"
    consensus.mkdir()
    output = tmp_path / "output"
    output.mkdir()
    return tmp_path


@pytest.fixture
def minimal_config_dict() -> dict:
    """Return a minimal configuration dictionary for testing."""
    return {
        "trial": {
            "n_subjects": 300,
            "randomization_ratio": "2:1",
            "seed": 12345,
        },
        "docker": {
            "image": "omni-r-clinical:latest",
            "memory_limit": "2g",
            "cpu_count": 1,
            "timeout": 300,
            "network_disabled": True,
        },
        "llm": {
            "gemini": {
                "api_key": "test-gemini-key",
                "model": "gemini-2.5-pro",
                "temperature": 0.0,
            },
            "openai": {
                "api_key": "test-openai-key",
                "model": "gpt-4o",
                "temperature": 0.0,
            },
        },
        "output_dir": "./output",
    }
