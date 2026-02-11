"""Docker-based R code execution engine."""

from omni_agents.docker.engine import DockerEngine
from omni_agents.docker.r_executor import RExecutor
from omni_agents.models.execution import DockerResult

__all__ = ["DockerEngine", "DockerResult", "RExecutor"]
