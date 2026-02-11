"""R script execution in Docker containers with resource limits.

RExecutor runs arbitrary R code in sandboxed Docker containers with:
- Memory and CPU limits
- Network isolation (disabled by default)
- Timeout enforcement
- Separate stdout/stderr capture
- Guaranteed container cleanup (no orphans)

Per PITFALLS.md:
- Never use auto_remove=True (need logs before removal) [DOCK-05]
- Always remove containers in a finally block [DOCK-05]
- Use separate stdout/stderr capture calls for reliable demux [DOCK-04]
- Network disabled by default to prevent LLM-generated code from making network calls [DOCK-03]
"""

from __future__ import annotations

import logging
import time
from pathlib import Path

import docker.errors

from omni_agents.docker.engine import DockerEngine
from omni_agents.models.execution import DockerResult

logger = logging.getLogger(__name__)


class RExecutor:
    """Execute R scripts inside Docker containers with resource limits.

    Uses DockerEngine for container lifecycle management. Each call to
    execute() creates a new container, runs the R script, captures output,
    and removes the container -- guaranteed cleanup via finally block.

    Args:
        engine: DockerEngine instance for Docker client access.
        image: Docker image name to run containers from.
        memory_limit: Container memory limit (e.g., "2g", "512m").
        cpu_count: Number of CPUs allocated to the container.
        timeout: Maximum execution time in seconds before killing the container.
        network_disabled: If True, run containers with network disabled.
    """

    def __init__(
        self,
        engine: DockerEngine,
        image: str = "omni-r-clinical:latest",
        memory_limit: str = "2g",
        cpu_count: int = 1,
        timeout: int = 300,
        network_disabled: bool = True,
    ) -> None:
        self._engine = engine
        self._image = image
        self._memory_limit = memory_limit
        self._cpu_count = cpu_count
        self._timeout = timeout
        self._network_disabled = network_disabled

    def execute(
        self,
        code: str,
        work_dir: Path,
        input_volumes: dict[str, str] | None = None,
    ) -> DockerResult:
        """Execute R code in a Docker container.

        Writes the R code to a script file in work_dir, mounts it into
        the container, runs it, and captures stdout/stderr separately.

        Args:
            code: R source code to execute.
            work_dir: Host directory to mount as /workspace (read-write).
                The R script is written here as script.R.
            input_volumes: Optional additional volume mounts.
                Keys are host paths, values are container mount points.
                These are mounted as read-only.

        Returns:
            DockerResult with exit_code, stdout, stderr, duration, and timed_out.
        """
        # Write R code to script file in the working directory
        script_path = work_dir / "script.R"
        script_path.write_text(code, encoding="utf-8")

        # Build volume mounts
        volumes = self._build_volumes(work_dir, input_volumes)

        # Determine network mode
        network_mode = "none" if self._network_disabled else "bridge"

        client = self._engine.get_client()
        container = None
        timed_out = False
        start_time = time.monotonic()

        try:
            # Create and start container (detached so we can enforce timeout)
            container = client.containers.run(
                image=self._image,
                command=["Rscript", "/workspace/script.R"],
                volumes=volumes,
                detach=True,
                stdout=True,
                stderr=True,
                mem_limit=self._memory_limit,
                nano_cpus=self._cpu_count * 1_000_000_000,
                network_mode=network_mode,
                labels={"org.omni-agents.component": "r-executor"},
            )

            logger.info(
                "Started container '%s' for R execution (image=%s, timeout=%ds)",
                container.short_id,
                self._image,
                self._timeout,
            )

            # Wait for completion with timeout
            try:
                result = container.wait(timeout=self._timeout)
                exit_code = result.get("StatusCode", -1)
            except (
                docker.errors.APIError,
                ConnectionError,
                Exception,
            ) as exc:
                # Timeout or connection error -- stop the container
                if "timed out" in str(exc).lower() or "read timeout" in str(exc).lower():
                    logger.warning(
                        "Container '%s' timed out after %ds, stopping",
                        container.short_id,
                        self._timeout,
                    )
                    timed_out = True
                    try:
                        container.stop(timeout=10)
                    except docker.errors.APIError:
                        container.kill()
                    exit_code = -1
                else:
                    raise

            duration = time.monotonic() - start_time

            # Capture stdout and stderr separately for reliable demux
            # (demux=True on container.logs() can be unreliable across Docker SDK versions)
            stdout_bytes = container.logs(stdout=True, stderr=False)
            stderr_bytes = container.logs(stdout=False, stderr=True)

            stdout_str = stdout_bytes.decode("utf-8", errors="replace") if stdout_bytes else ""
            stderr_str = stderr_bytes.decode("utf-8", errors="replace") if stderr_bytes else ""

            logger.info(
                "Container '%s' finished: exit_code=%d, duration=%.2fs, timed_out=%s",
                container.short_id,
                exit_code,
                duration,
                timed_out,
            )

            return DockerResult(
                exit_code=exit_code,
                stdout=stdout_str,
                stderr=stderr_str,
                duration_seconds=duration,
                timed_out=timed_out,
            )

        finally:
            # Always remove the container to prevent zombies (DOCK-05)
            if container is not None:
                try:
                    container.remove(force=True)
                    logger.debug(
                        "Removed container '%s'",
                        container.short_id,
                    )
                except docker.errors.APIError as exc:
                    logger.warning(
                        "Failed to remove container '%s': %s",
                        container.short_id,
                        exc,
                    )

    def _build_volumes(
        self,
        work_dir: Path,
        input_volumes: dict[str, str] | None,
    ) -> dict[str, dict[str, str]]:
        """Construct Docker volume mount dictionary.

        Args:
            work_dir: Host directory to mount as /workspace (read-write).
            input_volumes: Optional additional mounts (host_path -> container_path).
                These are mounted as read-only.

        Returns:
            Docker-formatted volume mount dictionary.
        """
        volumes: dict[str, dict[str, str]] = {
            str(work_dir.resolve()): {"bind": "/workspace", "mode": "rw"},
        }

        if input_volumes:
            for host_path, container_path in input_volumes.items():
                volumes[str(Path(host_path).resolve())] = {
                    "bind": container_path,
                    "mode": "ro",
                }

        return volumes
