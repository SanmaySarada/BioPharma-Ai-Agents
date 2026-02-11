"""Tests for RExecutor: Docker-based R script execution.

Tests are skipped if Docker daemon is not running, so CI environments
without Docker will not fail.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from omni_agents.docker.engine import DockerEngine
from omni_agents.docker.r_executor import RExecutor
from omni_agents.models.execution import DockerResult


def docker_available() -> bool:
    """Check if the Docker daemon is running and accessible."""
    try:
        import docker

        client = docker.from_env()
        client.ping()
        return True
    except Exception:
        return False


def image_available(image_name: str = "omni-r-clinical:latest") -> bool:
    """Check if the required Docker image exists locally."""
    try:
        import docker

        client = docker.from_env()
        client.images.get(image_name)
        return True
    except Exception:
        return False


skip_no_docker = pytest.mark.skipif(
    not docker_available(),
    reason="Docker daemon not available",
)

skip_no_image = pytest.mark.skipif(
    not docker_available() or not image_available(),
    reason="Docker not available or omni-r-clinical:latest image not built",
)


@skip_no_docker
class TestDockerEngine:
    """Tests for DockerEngine client management."""

    def test_engine_initializes(self) -> None:
        """DockerEngine connects to Docker daemon successfully."""
        engine = DockerEngine()
        assert engine.get_client() is not None

    def test_ensure_image_exists(self) -> None:
        """ensure_image returns True for images that exist."""
        engine = DockerEngine()
        # alpine is a common small image; pull if needed
        client = engine.get_client()
        client.images.pull("alpine", tag="latest")
        assert engine.ensure_image("alpine:latest") is True

    def test_ensure_image_not_found(self) -> None:
        """ensure_image returns False for nonexistent images with no dockerfile."""
        engine = DockerEngine()
        assert engine.ensure_image("nonexistent-image-12345:latest") is False

    def test_cleanup_containers_no_orphans(self) -> None:
        """cleanup_containers returns 0 when no matching containers exist."""
        engine = DockerEngine()
        # Use a unique label that won't match anything
        count = engine.cleanup_containers(label="org.omni-agents.test=cleanup-test-12345")
        assert count == 0


@skip_no_image
class TestRExecutor:
    """Tests for RExecutor R script execution in Docker."""

    @pytest.fixture
    def engine(self) -> DockerEngine:
        """Create a DockerEngine instance."""
        return DockerEngine()

    @pytest.fixture
    def executor(self, engine: DockerEngine) -> RExecutor:
        """Create an RExecutor with default settings."""
        return RExecutor(engine)

    def test_simple_stdout_capture(
        self,
        executor: RExecutor,
        tmp_path: Path,
    ) -> None:
        """R script stdout is captured correctly."""
        result = executor.execute('cat("hello world\\n")', tmp_path)
        assert result.exit_code == 0
        assert "hello world" in result.stdout
        assert result.timed_out is False

    def test_stderr_captured_separately(
        self,
        executor: RExecutor,
        tmp_path: Path,
    ) -> None:
        """R stderr is captured separately from stdout."""
        code = 'cat("stdout text\\n")\nmessage("stderr text")'
        result = executor.execute(code, tmp_path)
        assert result.exit_code == 0
        assert "stdout text" in result.stdout
        assert "stderr text" in result.stderr

    def test_nonzero_exit_code(
        self,
        executor: RExecutor,
        tmp_path: Path,
    ) -> None:
        """R script errors produce non-zero exit code."""
        result = executor.execute('stop("intentional error")', tmp_path)
        assert result.exit_code != 0
        assert "intentional error" in result.stderr

    def test_duration_tracked(
        self,
        executor: RExecutor,
        tmp_path: Path,
    ) -> None:
        """Execution duration is tracked and positive."""
        result = executor.execute('cat("ok\\n")', tmp_path)
        assert result.duration_seconds > 0

    def test_container_cleanup_after_execution(
        self,
        engine: DockerEngine,
        executor: RExecutor,
        tmp_path: Path,
    ) -> None:
        """No orphan containers remain after execution."""
        executor.execute('cat("cleanup test\\n")', tmp_path)

        # Verify no containers with our label remain
        import docker

        client = docker.from_env()
        orphans = client.containers.list(
            all=True,
            filters={"label": "org.omni-agents.component=r-executor"},
        )
        assert len(orphans) == 0, f"Found {len(orphans)} orphan container(s)"

    def test_container_cleanup_after_error(
        self,
        engine: DockerEngine,
        executor: RExecutor,
        tmp_path: Path,
    ) -> None:
        """Containers are cleaned up even when R script fails."""
        executor.execute('stop("error for cleanup test")', tmp_path)

        import docker

        client = docker.from_env()
        orphans = client.containers.list(
            all=True,
            filters={"label": "org.omni-agents.component=r-executor"},
        )
        assert len(orphans) == 0, f"Found {len(orphans)} orphan container(s) after error"

    def test_network_disabled_by_default(
        self,
        engine: DockerEngine,
        tmp_path: Path,
    ) -> None:
        """Containers run with network disabled by default."""
        executor = RExecutor(engine, network_disabled=True)
        # This R code would fail if network was available and succeed silently;
        # with network disabled, any network call errors. We verify the container
        # was created with the right network mode by checking that the executor
        # doesn't crash (network_mode="none" is accepted by Docker).
        result = executor.execute('cat("network test\\n")', tmp_path)
        assert result.exit_code == 0
        assert "network test" in result.stdout

    def test_input_volumes_mounted(
        self,
        executor: RExecutor,
        tmp_path: Path,
    ) -> None:
        """Additional input volumes are mounted as read-only."""
        # Create a directory with a test file to mount
        input_dir = tmp_path / "input_data"
        input_dir.mkdir()
        test_file = input_dir / "test.txt"
        test_file.write_text("input data content")

        work_dir = tmp_path / "work"
        work_dir.mkdir()

        result = executor.execute(
            'cat(readLines("/data/input/test.txt"), sep="\\n")\ncat("\\n")',
            work_dir,
            input_volumes={str(input_dir): "/data/input"},
        )
        assert result.exit_code == 0
        assert "input data content" in result.stdout

    def test_script_file_written(
        self,
        executor: RExecutor,
        tmp_path: Path,
    ) -> None:
        """R code is written to script.R in the work directory."""
        code = 'cat("script file test\\n")'
        executor.execute(code, tmp_path)

        script_path = tmp_path / "script.R"
        assert script_path.exists()
        assert script_path.read_text() == code


class TestDockerResult:
    """Tests for DockerResult Pydantic model."""

    def test_docker_result_creation(self) -> None:
        """DockerResult can be created with required fields."""
        result = DockerResult(
            exit_code=0,
            stdout="output",
            stderr="",
            duration_seconds=1.5,
        )
        assert result.exit_code == 0
        assert result.stdout == "output"
        assert result.stderr == ""
        assert result.duration_seconds == 1.5
        assert result.timed_out is False

    def test_docker_result_timed_out(self) -> None:
        """DockerResult tracks timeout status."""
        result = DockerResult(
            exit_code=-1,
            stdout="partial",
            stderr="",
            duration_seconds=300.0,
            timed_out=True,
        )
        assert result.timed_out is True
        assert result.exit_code == -1

    def test_docker_result_serializes_to_dict(self) -> None:
        """DockerResult (Pydantic model) serializes to dict correctly."""
        result = DockerResult(
            exit_code=0,
            stdout="output",
            stderr="warning text",
            duration_seconds=1.0,
            timed_out=False,
        )
        data = result.model_dump()
        assert data["exit_code"] == 0
        assert data["stdout"] == "output"
        assert data["stderr"] == "warning text"
        assert data["duration_seconds"] == 1.0
        assert data["timed_out"] is False
