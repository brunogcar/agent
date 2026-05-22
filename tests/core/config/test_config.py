"""
tests/core/config/test_config.py
Tests for the centralized Config singleton, ensuring magic numbers
and limits are correctly loaded and can be overridden via environment variables.

Uses two testing strategies:
- Constructor tests: instantiate fresh Config() to verify defaults and env parsing
- Integration tests: use monkeypatch.setattr on the singleton to test production paths
"""
import pytest
from core.config import cfg, Config


# =============================================================================
# Constructor Tests — verify defaults and env parsing via fresh Config()
# =============================================================================
class TestConfigConstructorDefaults:
    """Test that Config() constructor parses defaults correctly."""

    def test_memory_limits_default(self, monkeypatch):
        # Ensure env vars are unset so we get defaults
        for key in ["MAX_MEMORY_BYTES", "MAX_TAGS_PER_ENTRY", "MAX_TAG_LENGTH"]:
            monkeypatch.delenv(key, raising=False)
        c = Config()
        assert c.memory_max_entry_bytes == 50000
        assert c.max_tags_per_entry == 6
        assert c.max_tag_length == 50

    def test_web_limits_default(self, monkeypatch):
        for key in ["WEB_MAX_TEXT_CHARS", "WEB_SNIPPET_CHARS", "WEB_MAX_SEARCH_RESULTS"]:
            monkeypatch.delenv(key, raising=False)
        c = Config()
        assert c.web_max_text_chars == 8000
        assert c.web_snippet_chars == 300
        assert c.web_max_search_results == 10

    def test_cli_limits_default(self, monkeypatch):
        for key in ["CLI_MAX_COMMAND_LENGTH", "CLI_MAX_ARGUMENTS"]:
            monkeypatch.delenv(key, raising=False)
        c = Config()
        assert c.cli_max_command_chars == 4096  # Updated default from 1024
        assert c.cli_max_arguments == 20

    def test_cli_env_override(self, monkeypatch):
        monkeypatch.setenv("CLI_MAX_COMMAND_LENGTH", "8192")
        c = Config()
        assert c.cli_max_command_chars == 8192

    def test_web_env_override(self, monkeypatch):
        monkeypatch.setenv("WEB_MAX_TEXT_CHARS", "16000")
        monkeypatch.setenv("WEB_MAX_SEARCH_RESULTS", "20")
        c = Config()
        assert c.web_max_text_chars == 16000
        assert c.web_max_search_results == 20

    def test_memory_env_override(self, monkeypatch):
        monkeypatch.setenv("MAX_MEMORY_BYTES", "100000")
        monkeypatch.setenv("MAX_TAGS_PER_ENTRY", "10")
        c = Config()
        assert c.memory_max_entry_bytes == 100000
        assert c.max_tags_per_entry == 10


# =============================================================================
# Validation Tests — verify invalid env vars are rejected
# =============================================================================
class TestConfigValidation:
    """Test that Config() rejects invalid values with explicit ValueError."""

    def test_negative_memory_limit(self, monkeypatch):
        monkeypatch.setenv("MAX_MEMORY_BYTES", "-1")
        with pytest.raises(ValueError, match="MAX_MEMORY_BYTES"):
            Config()

    def test_zero_memory_limit(self, monkeypatch):
        monkeypatch.setenv("MAX_MEMORY_BYTES", "0")
        with pytest.raises(ValueError, match="MAX_MEMORY_BYTES"):
            Config()

    def test_extreme_memory_limit(self, monkeypatch):
        monkeypatch.setenv("MAX_MEMORY_BYTES", "999999999")
        with pytest.raises(ValueError, match="MAX_MEMORY_BYTES"):
            Config()

    def test_non_numeric_memory(self, monkeypatch):
        monkeypatch.setenv("MAX_MEMORY_BYTES", "not_a_number")
        with pytest.raises(ValueError):  # int() will raise ValueError
            Config()

    def test_negative_cli_command_length(self, monkeypatch):
        monkeypatch.setenv("CLI_MAX_COMMAND_LENGTH", "-100")
        with pytest.raises(ValueError, match="CLI_MAX_COMMAND_LENGTH"):
            Config()

    def test_zero_cli_command_length(self, monkeypatch):
        monkeypatch.setenv("CLI_MAX_COMMAND_LENGTH", "0")
        with pytest.raises(ValueError, match="CLI_MAX_COMMAND_LENGTH"):
            Config()

    def test_extreme_cli_command_length(self, monkeypatch):
        monkeypatch.setenv("CLI_MAX_COMMAND_LENGTH", "999999")
        with pytest.raises(ValueError, match="CLI_MAX_COMMAND_LENGTH"):
            Config()

    def test_negative_web_chars(self, monkeypatch):
        monkeypatch.setenv("WEB_MAX_TEXT_CHARS", "-500")
        with pytest.raises(ValueError, match="WEB_MAX_TEXT_CHARS"):
            Config()

    def test_zero_web_chars(self, monkeypatch):
        monkeypatch.setenv("WEB_MAX_TEXT_CHARS", "0")
        with pytest.raises(ValueError, match="WEB_MAX_TEXT_CHARS"):
            Config()

    def test_zero_tags(self, monkeypatch):
        monkeypatch.setenv("MAX_TAGS_PER_ENTRY", "0")
        with pytest.raises(ValueError, match="MAX_TAGS_PER_ENTRY"):
            Config()


# =============================================================================
# Integration Tests — use monkeypatch.setattr on the singleton
# Tests the actual production code path (tools use the singleton they imported)
# =============================================================================
class TestConfigIntegration:
    """Test that patching the singleton affects tool behavior."""

    def test_singleton_patching_affects_readers(self, monkeypatch):
        """Tools that imported cfg see the patched values."""
        original = cfg.web_max_text_chars
        try:
            monkeypatch.setattr(cfg, "web_max_text_chars", 1000)
            # Any code that does `cfg.web_max_text_chars` will see 1000
            assert cfg.web_max_text_chars == 1000
        finally:
            # monkeypatch auto-restores, but be explicit
            assert cfg.web_max_text_chars == original

    def test_singleton_patching_cli(self, monkeypatch):
        original = cfg.cli_max_command_chars
        try:
            monkeypatch.setattr(cfg, "cli_max_command_chars", 500)
            assert cfg.cli_max_command_chars == 500
        finally:
            assert cfg.cli_max_command_chars == original

    def test_singleton_patching_memory(self, monkeypatch):
        original = cfg.memory_max_entry_bytes
        try:
            monkeypatch.setattr(cfg, "memory_max_entry_bytes", 75000)
            assert cfg.memory_max_entry_bytes == 75000
        finally:
            assert cfg.memory_max_entry_bytes == original


# =============================================================================
# Naming Tests — verify renames from consensus D1 Option B
# =============================================================================
class TestConfigNaming:
    """Verify the D1 Option B naming convention is applied."""

    def test_cli_uses_chars_not_length(self):
        """cli_max_command_chars (not cli_max_command_length)"""
        assert hasattr(cfg, "cli_max_command_chars")
        assert not hasattr(cfg, "cli_max_command_length")

    def test_memory_clarifies_entry_scope(self):
        """memory_max_entry_bytes (not max_memory_bytes)"""
        assert hasattr(cfg, "memory_max_entry_bytes")
        assert not hasattr(cfg, "max_memory_bytes")

    def test_web_limits_use_chars_suffix(self):
        assert hasattr(cfg, "web_max_text_chars")
        assert hasattr(cfg, "web_snippet_chars")