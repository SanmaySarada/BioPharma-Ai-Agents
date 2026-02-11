"""Tests for ScriptCache: cache key computation, hit/miss, and roundtrip."""

from omni_agents.config import TrialConfig
from omni_agents.pipeline.script_cache import ScriptCache


class TestScriptCache:
    """Unit tests for ScriptCache get/put and cache_key."""

    def test_cache_miss_returns_none(self, tmp_path):
        """A fresh cache returns None for any key."""
        cache = ScriptCache(cache_dir=tmp_path / "cache")
        assert cache.get("nonexistent") is None

    def test_put_and_get_roundtrip(self, tmp_path):
        """put() then get() returns identical code."""
        cache = ScriptCache(cache_dir=tmp_path / "cache")
        code = "set.seed(42)\nprint('hello')\n"
        cache.put("test_key", code)
        assert cache.get("test_key") == code

    def test_cache_key_deterministic(self):
        """Same TrialConfig + agent_name produces the same key every time."""
        config = TrialConfig()
        key1 = ScriptCache.cache_key(config, "simulator")
        key2 = ScriptCache.cache_key(config, "simulator")
        assert key1 == key2

    def test_cache_key_differs_on_seed_change(self):
        """Two TrialConfigs differing only in seed produce different keys."""
        config_a = TrialConfig(seed=12345)
        config_b = TrialConfig(seed=99999)
        key_a = ScriptCache.cache_key(config_a, "simulator")
        key_b = ScriptCache.cache_key(config_b, "simulator")
        assert key_a != key_b

    def test_cache_key_differs_on_agent_name(self):
        """Same TrialConfig with different agent_name produces different keys."""
        config = TrialConfig()
        key_sim = ScriptCache.cache_key(config, "simulator")
        key_sdtm = ScriptCache.cache_key(config, "sdtm")
        assert key_sim != key_sdtm

    def test_put_creates_file_on_disk(self, tmp_path):
        """After put(), the .R file exists at the expected path."""
        cache = ScriptCache(cache_dir=tmp_path / "cache")
        code = "library(survival)\n"
        returned_path = cache.put("disk_check", code)

        expected_path = tmp_path / "cache" / "disk_check.R"
        assert expected_path.exists()
        assert expected_path == returned_path
        assert expected_path.read_text() == code
