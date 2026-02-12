"""R script caching for reproducible pipeline runs.

Caches generated R scripts keyed on a hash of the trial configuration,
so that subsequent runs with identical config reuse the same code --
guaranteeing identical output when combined with set.seed() injection.
"""

import hashlib
from pathlib import Path

from loguru import logger

from omni_agents.config import TrialConfig


class ScriptCache:
    """Cache for generated R scripts, keyed on trial config hash.

    The cache key is derived from the full TrialConfig (including seed)
    plus the agent name, so any config change causes a cache miss and
    fresh LLM generation.
    """

    def __init__(self, cache_dir: Path) -> None:
        self.cache_dir = cache_dir
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def cache_key(trial_config: TrialConfig, agent_name: str, track_id: str = "") -> str:
        """Compute a deterministic cache key from trial config, agent, and track.

        The track_id parameter prevents cache collisions between tracks in the
        symmetric double programming architecture. Different tracks using the
        same agent and config will produce different cache keys.

        Args:
            trial_config: The trial configuration to hash.
            agent_name: Agent identifier (e.g. "simulator") to distinguish
                scripts from different agents.
            track_id: Track identifier (e.g. "track_a", "track_b"). Defaults
                to empty string for backward compatibility with agents that
                have no track (e.g. Simulator).

        Returns:
            First 16 characters of the SHA-256 hex digest.
        """
        payload = trial_config.model_dump_json() + "|" + agent_name + "|" + track_id
        return hashlib.sha256(payload.encode()).hexdigest()[:16]

    def get(self, key: str) -> str | None:
        """Retrieve a cached R script by key.

        Args:
            key: Cache key (from :meth:`cache_key`).

        Returns:
            The cached R code string, or None on cache miss.
        """
        path = self.cache_dir / f"{key}.R"
        if path.exists():
            logger.info(f"Script cache hit: {key}")
            return path.read_text()
        return None

    def put(self, key: str, code: str) -> Path:
        """Store an R script in the cache.

        Args:
            key: Cache key (from :meth:`cache_key`).
            code: The R code to cache.

        Returns:
            Path to the cached file.
        """
        path = self.cache_dir / f"{key}.R"
        path.write_text(code)
        logger.info(f"Script cached: {key}")
        return path
