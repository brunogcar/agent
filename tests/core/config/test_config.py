"""
tests/core/config/test_config.py
Tests for the centralized Config singleton, ensuring magic numbers 
and limits are correctly loaded and can be overridden via environment variables.
"""
import pytest
import importlib
import sys
import os

@pytest.fixture
def reload_config(monkeypatch):
    """
    Helper fixture to safely reload core.config with custom env vars.
    This is necessary because `cfg` is a singleton instantiated at import time.
    """
    def _reload(env_vars: dict):
        for k, v in env_vars.items():
            monkeypatch.setenv(k, str(v))
        
        # Remove from sys.modules to force a fresh import
        if "core.config" in sys.modules:
            del sys.modules["core.config"]
            
        import core.config
        importlib.reload(core.config)
        return core.config.cfg
        
    yield _reload
    
    # Cleanup: reload again with default env to restore the global singleton
    if "core.config" in sys.modules:
        del sys.modules["core.config"]
    import core.config
    importlib.reload(core.config)

class TestConfigDefaults:
    def test_memory_limits_default(self, reload_config):
        cfg = reload_config({})
        assert cfg.max_memory_bytes == 50000
        assert cfg.max_tags_per_entry == 6
        assert cfg.max_tag_length == 50

    def test_web_limits_default(self, reload_config):
        cfg = reload_config({})
        assert cfg.web_max_text_chars == 8000
        assert cfg.web_snippet_chars == 300
        assert cfg.web_max_search_results == 10

    def test_cli_limits_default(self, reload_config):
        cfg = reload_config({})
        assert cfg.cli_max_command_length == 1024
        assert cfg.cli_max_arguments == 20

class TestConfigOverrides:
    def test_memory_override(self, reload_config):
        cfg = reload_config({
            "MAX_MEMORY_BYTES": "100000",
            "MAX_TAGS_PER_ENTRY": "10"
        })
        assert cfg.max_memory_bytes == 100000
        assert cfg.max_tags_per_entry == 10

    def test_web_override(self, reload_config):
        cfg = reload_config({
            "WEB_MAX_TEXT_CHARS": "16000",
            "WEB_MAX_SEARCH_RESULTS": "20"
        })
        assert cfg.web_max_text_chars == 16000
        assert cfg.web_max_search_results == 20