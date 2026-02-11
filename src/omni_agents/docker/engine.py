"""Docker client management and image building.

Provides DockerEngine for container lifecycle management,
image availability checks, and cleanup of orphaned containers.
"""

from __future__ import annotations

import logging
from pathlib import Path

import docker
from docker.errors import DockerException, ImageNotFound

logger = logging.getLogger(__name__)


class DockerEngine:
    """Manages Docker client lifecycle, image building, and container cleanup.

    DockerEngine is the single point of contact with the Docker daemon.
    RExecutor uses DockerEngine for all container operations.
    """

    def __init__(self) -> None:
        """Initialize Docker client from environment.

        Raises:
            DockerException: If Docker daemon is not running or not accessible.
        """
        self._client = docker.from_env()
        # Verify connectivity
        self._client.ping()
        logger.info("DockerEngine initialized, connected to Docker daemon")

    def ensure_image(
        self,
        image_name: str,
        dockerfile_path: Path | None = None,
    ) -> bool:
        """Check if a Docker image exists locally; build it if not.

        Args:
            image_name: Full image name with tag (e.g., "omni-r-clinical:latest").
            dockerfile_path: Path to directory containing the Dockerfile.
                If provided and image doesn't exist, builds from this path.

        Returns:
            True if the image is available (existed or was built successfully).

        Raises:
            docker.errors.BuildError: If the image build fails.
        """
        try:
            self._client.images.get(image_name)
            logger.info("Image '%s' found locally", image_name)
            return True
        except ImageNotFound:
            logger.info("Image '%s' not found locally", image_name)

        if dockerfile_path is None:
            logger.warning(
                "Image '%s' not found and no dockerfile_path provided",
                image_name,
            )
            return False

        # Parse image name into repository:tag
        if ":" in image_name:
            tag = image_name
        else:
            tag = f"{image_name}:latest"

        logger.info(
            "Building image '%s' from '%s'",
            tag,
            dockerfile_path,
        )
        self._client.images.build(
            path=str(dockerfile_path),
            tag=tag,
            rm=True,
        )
        logger.info("Image '%s' built successfully", tag)
        return True

    def cleanup_containers(
        self,
        label: str = "org.omni-agents.component=r-executor",
    ) -> int:
        """Find and remove all containers with the given label.

        Uses force=True to handle stuck containers.

        Args:
            label: Docker label filter string (e.g., "key=value").

        Returns:
            Number of containers removed.
        """
        containers = self._client.containers.list(
            all=True,
            filters={"label": label},
        )
        count = 0
        for container in containers:
            try:
                container.remove(force=True)
                logger.info(
                    "Removed container '%s' (%s)",
                    container.name,
                    container.short_id,
                )
                count += 1
            except DockerException as exc:
                logger.warning(
                    "Failed to remove container '%s': %s",
                    container.name,
                    exc,
                )
        if count > 0:
            logger.info("Cleaned up %d orphaned container(s)", count)
        return count

    def get_client(self) -> docker.DockerClient:
        """Return the underlying Docker client for direct use by RExecutor.

        Returns:
            The docker.DockerClient instance.
        """
        return self._client
