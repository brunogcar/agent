"""Tests for core/config_validation.py — startup config validation (Bug #17).

Verifies that validate_config() catches:
  - model_registry entries with empty model/provider strings
  - model_registry entries with invalid timeouts
  - agent roles with llm_role not in model_registry (typos)
  - malformed allowed_internal_hosts SSRF config
"""
from __future__ import annotations

from unittest.mock import patch, MagicMock

import pytest

from core.config_validation import validate_config


class TestModelRegistryValidation:
    """model_registry entries must have non-empty model, provider, and positive timeout."""

    def test_empty_model_string_caught(self):
        """An entry with empty 'model' must be reported as an error."""
        fake_cfg = MagicMock()
        fake_cfg.agent_root = MagicMock(exists=lambda: True)
        fake_cfg.workspace_root = MagicMock(exists=lambda: True)
        fake_cfg.memory_root = MagicMock(exists=lambda: True)
        fake_cfg.memory_chroma_path = MagicMock(exists=lambda: True)
        fake_cfg.workspace_autocode = MagicMock(exists=lambda: True)
        fake_cfg.workspace_index = MagicMock(exists=lambda: True)
        fake_cfg.log_path = MagicMock(exists=lambda: True)
        fake_cfg.planner_model = "test"
        fake_cfg.executor_model = "test"
        fake_cfg.router_model = "test"
        fake_cfg.sandbox_timeout = 30
        fake_cfg.execution_timeout = 120
        fake_cfg.planner_timeout = 180
        fake_cfg.router_timeout = 15
        fake_cfg.autocode_graph_timeout = 60
        fake_cfg.autocode_max_retries = 3
        fake_cfg.autocode_max_file_chars = 10000
        fake_cfg.lm_studio_base_url = "http://localhost:1234/v1"
        fake_cfg.model_registry = {
            "planner": {"model": "", "provider": "lmstudio", "timeout": 180},
        }
        fake_cfg.allowed_internal_hosts = frozenset({"localhost"})

        with patch("core.config_validation.cfg", fake_cfg), \
             patch("core.config_validation.tracer"):
            with pytest.raises(RuntimeError, match="empty 'model'"):
                validate_config()

    def test_empty_provider_string_caught(self):
        """An entry with empty 'provider' must be reported as an error."""
        fake_cfg = MagicMock()
        fake_cfg.agent_root = MagicMock(exists=lambda: True)
        fake_cfg.workspace_root = MagicMock(exists=lambda: True)
        fake_cfg.memory_root = MagicMock(exists=lambda: True)
        fake_cfg.memory_chroma_path = MagicMock(exists=lambda: True)
        fake_cfg.workspace_autocode = MagicMock(exists=lambda: True)
        fake_cfg.workspace_index = MagicMock(exists=lambda: True)
        fake_cfg.log_path = MagicMock(exists=lambda: True)
        fake_cfg.planner_model = "test"
        fake_cfg.executor_model = "test"
        fake_cfg.router_model = "test"
        fake_cfg.sandbox_timeout = 30
        fake_cfg.execution_timeout = 120
        fake_cfg.planner_timeout = 180
        fake_cfg.router_timeout = 15
        fake_cfg.autocode_graph_timeout = 60
        fake_cfg.autocode_max_retries = 3
        fake_cfg.autocode_max_file_chars = 10000
        fake_cfg.lm_studio_base_url = "http://localhost:1234/v1"
        fake_cfg.model_registry = {
            "planner": {"model": "test-model", "provider": "", "timeout": 180},
        }
        fake_cfg.allowed_internal_hosts = frozenset({"localhost"})

        with patch("core.config_validation.cfg", fake_cfg), \
             patch("core.config_validation.tracer"):
            with pytest.raises(RuntimeError, match="empty 'provider'"):
                validate_config()

    def test_invalid_timeout_caught(self):
        """An entry with timeout <= 0 must be reported as an error."""
        fake_cfg = MagicMock()
        fake_cfg.agent_root = MagicMock(exists=lambda: True)
        fake_cfg.workspace_root = MagicMock(exists=lambda: True)
        fake_cfg.memory_root = MagicMock(exists=lambda: True)
        fake_cfg.memory_chroma_path = MagicMock(exists=lambda: True)
        fake_cfg.workspace_autocode = MagicMock(exists=lambda: True)
        fake_cfg.workspace_index = MagicMock(exists=lambda: True)
        fake_cfg.log_path = MagicMock(exists=lambda: True)
        fake_cfg.planner_model = "test"
        fake_cfg.executor_model = "test"
        fake_cfg.router_model = "test"
        fake_cfg.sandbox_timeout = 30
        fake_cfg.execution_timeout = 120
        fake_cfg.planner_timeout = 180
        fake_cfg.router_timeout = 15
        fake_cfg.autocode_graph_timeout = 60
        fake_cfg.autocode_max_retries = 3
        fake_cfg.autocode_max_file_chars = 10000
        fake_cfg.lm_studio_base_url = "http://localhost:1234/v1"
        fake_cfg.model_registry = {
            "planner": {"model": "test-model", "provider": "lmstudio", "timeout": 0},
        }
        fake_cfg.allowed_internal_hosts = frozenset({"localhost"})

        with patch("core.config_validation.cfg", fake_cfg), \
             patch("core.config_validation.tracer"):
            with pytest.raises(RuntimeError, match="invalid 'timeout'"):
                validate_config()


class TestAllowedInternalHostsValidation:
    """allowed_internal_hosts must be a frozenset of non-empty strings."""

    def test_non_set_type_caught(self):
        """A non-set/list type must be reported as an error."""
        fake_cfg = MagicMock()
        fake_cfg.agent_root = MagicMock(exists=lambda: True)
        fake_cfg.workspace_root = MagicMock(exists=lambda: True)
        fake_cfg.memory_root = MagicMock(exists=lambda: True)
        fake_cfg.memory_chroma_path = MagicMock(exists=lambda: True)
        fake_cfg.workspace_autocode = MagicMock(exists=lambda: True)
        fake_cfg.workspace_index = MagicMock(exists=lambda: True)
        fake_cfg.log_path = MagicMock(exists=lambda: True)
        fake_cfg.planner_model = "test"
        fake_cfg.executor_model = "test"
        fake_cfg.router_model = "test"
        fake_cfg.sandbox_timeout = 30
        fake_cfg.execution_timeout = 120
        fake_cfg.planner_timeout = 180
        fake_cfg.router_timeout = 15
        fake_cfg.autocode_graph_timeout = 60
        fake_cfg.autocode_max_retries = 3
        fake_cfg.autocode_max_file_chars = 10000
        fake_cfg.lm_studio_base_url = "http://localhost:1234/v1"
        fake_cfg.model_registry = {
            "planner": {"model": "test-model", "provider": "lmstudio", "timeout": 180},
        }
        # Pass a string instead of a set — invalid type
        fake_cfg.allowed_internal_hosts = "localhost"

        with patch("core.config_validation.cfg", fake_cfg), \
             patch("core.config_validation.tracer"):
            with pytest.raises(RuntimeError, match="allowed_internal_hosts must be"):
                validate_config()
