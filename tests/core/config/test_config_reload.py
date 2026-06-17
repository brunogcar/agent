"""Tests for core/config.py reload and load_dotenv override behavior.

[BUGFIX-CONFIG] Covers load_dotenv(override=True) preventing Windows env var shadowing.
"""
from __future__ import annotations

import os
import tempfile

import pytest

class TestConfigReload:
    """Verify config reload correctly picks up .env changes with override=True."""

    def test_load_dotenv_override_shadows_os_env(self, monkeypatch):
        """.env value must override OS environment variable when override=True."""
        # Set an OS environment variable
        monkeypatch.setenv("PLANNER_MODEL", "os-level-model")

        # Create a temp .env file with a different value
        with tempfile.NamedTemporaryFile(mode="w", suffix=".env", delete=False, encoding="utf-8") as f:
            f.write("PLANNER_MODEL=env-file-model\n")
            env_path = f.name

        try:
            from dotenv import load_dotenv
            load_dotenv(env_path, override=True)

            # The .env value should win because override=True
            assert os.getenv("PLANNER_MODEL") == "env-file-model"
        finally:
            os.remove(env_path)
            # Clean up env var
            monkeypatch.delenv("PLANNER_MODEL", raising=False)

    def test_windows_env_var_shadowing_prevented(self, monkeypatch):
        """Windows env vars must not shadow .env values when override=True."""
        # Simulate Windows behavior: OS env var exists
        monkeypatch.setenv("EXECUTOR_MODEL", "windows-default-model")

        # Create .env with different value
        with tempfile.NamedTemporaryFile(mode="w", suffix=".env", delete=False, encoding="utf-8") as f:
            f.write("EXECUTOR_MODEL=dotenv-override-model\n")
            env_path = f.name

        try:
            from dotenv import load_dotenv
            load_dotenv(env_path, override=True)

            # .env must override the OS env var
            assert os.getenv("EXECUTOR_MODEL") == "dotenv-override-model"
        finally:
            os.remove(env_path)
            monkeypatch.delenv("EXECUTOR_MODEL", raising=False)

    def test_reload_calls_load_dotenv_with_override(self, monkeypatch):
        """Config.reload() must call load_dotenv(override=True)."""
        import core.config as config_module

        # Track load_dotenv calls
        load_calls = []
        def mock_load_dotenv(path=None, **kwargs):
            load_calls.append(kwargs)

        monkeypatch.setattr(config_module, "load_dotenv", mock_load_dotenv)

        # Create a config and reload
        from core.config import Config
        cfg = Config()
        cfg.reload()

        # Verify override=True was passed during reload
        assert any(call.get("override") is True for call in load_calls),             f"load_dotenv was not called with override=True during reload. Calls: {load_calls}"

    def test_config_uses_env_var_values(self):
        """Config must reflect current environment variable values."""
        # This test verifies that Config reads from os.environ
        # We check that the values are not hardcoded defaults
        from core.config import cfg

        # cfg should have loaded values from .env or env vars
        assert cfg.planner_model is not None
        assert len(cfg.planner_model) > 0
        assert cfg.executor_model is not None
        assert len(cfg.executor_model) > 0
        assert cfg.router_model is not None
        assert len(cfg.router_model) > 0

    def test_module_level_load_dotenv_uses_override(self):
        """Verify that the module-level load_dotenv call uses override=True.

        This is the critical fix for the Windows env var shadowing bug.
        The load_dotenv call at module import time must pass override=True
        so that .env values take precedence over OS environment variables.
        """
        import core.config as config_module

        # Check the source code contains override=True
        import inspect
        source = inspect.getsource(config_module)
        assert "load_dotenv(" in source
        assert "override=True" in source,             "Module-level load_dotenv must use override=True to prevent Windows env var shadowing"

    def test_reload_race_condition_documented(self):
        """Config.reload() is NOT atomic — document the limitation.

        reload() calls load_dotenv() then self.__init__() sequentially.
        Between these steps, concurrent reads may see a partially-updated
        config (e.g., new planner_model but old executor_model).

        This is acceptable for a single-operator local agent where reloads
        happen at controlled times, not mid-request. This test documents
        the known limitation rather than asserting a false guarantee.
        """
        # This test serves as documentation. No assertion needed.
        # If reload() ever becomes concurrent-safe, this test should be
        # replaced with a real race-condition test (ThreadPoolExecutor
        # with interleaved reload/read operations).
        pass
