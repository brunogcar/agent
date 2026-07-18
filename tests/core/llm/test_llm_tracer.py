"""Unit tests for tracer integration in LLMClient.

[BUGFIX-1] Covers the tracer.log() -> tracer.step() fix in circuit_breaker_states.
"""
from __future__ import annotations

import pytest
from unittest.mock import Mock, patch, MagicMock

from core.llm_backend.client import LLMClient
from core.llm_backend.provider import BaseProvider


@pytest.fixture
def mock_config():
    """Mock configuration for LLM client."""
    with patch("core.llm_backend.config.cfg") as mock_cfg:
        mock_cfg.lm_studio_base_url = "http://localhost:1234/v1"
        mock_cfg.executor_model = "test-model"
        mock_cfg.vision_model = "test-vision-model"
        mock_cfg.model_registry = {
            "executor": {"model": "test-model", "timeout": 120, "provider": "lmstudio"},
            "planner": {"model": "test-model", "timeout": 90, "provider": "lmstudio"},
            "router": {"model": "test-model", "timeout": 15, "provider": "lmstudio"},
            "consultor": {"model": "test-model", "timeout": 60, "provider": "openai"},
        }
        mock_cfg.max_context_tokens = 8000
        mock_cfg.enable_metrics_endpoint = False
        yield mock_cfg


@pytest.fixture
def llm_client(mock_config):
    """Create an LLM client with mocked config."""
    return LLMClient()


class TestTracerIntegration:
    """Verify tracer.step() is used correctly — never tracer.log()."""

    def test_circuit_breaker_states_uses_tracer_step(self, llm_client):
        """[BUGFIX-1] circuit_breaker_states must call tracer.step(), not tracer.log().

        [v1.1 UPDATE] The trace_id is now a unique hex ID from tracer.new_trace(),
        not the old empty string "". The test verifies that:
          - tracer.step() is called (not tracer.log())
          - the trace_id is a non-empty 12-char hex string (not "" or a literal)
          - the node is "circuit_breaker"
          - the role kwarg is present
        See: docs/core/observability/CHANGELOG.md (v1.1)
        """
        with patch("core.llm_backend.client.tracer.step") as mock_step, \
             patch("core.llm_backend.client.tracer.error") as mock_error, \
             patch("core.llm_backend.client.tracer.new_trace", return_value="abc123def456") as mock_new:
            states = llm_client.circuit_breaker_states
            # Should call tracer.step for each role
            assert mock_step.called, "tracer.step() was never called"
            # new_trace should have been called once to create the sweep trace
            mock_new.assert_called_once()
            # Verify the call signature: step(trace_id, "circuit_breaker", role=..., ...)
            call_args = mock_step.call_args
            trace_id = call_args[0][0]
            assert trace_id == "abc123def456"  # unique trace_id, not "" or a literal
            assert len(trace_id) == 12  # 12-char hex
            assert call_args[0][1] == "circuit_breaker"  # node
            assert "role" in call_args[1]  # role kwarg
            # Must NOT call tracer.log() — that method does not exist
            # (If the old buggy code ran, this would raise AttributeError)

    def test_circuit_breaker_states_returns_none_when_metrics_disabled(self, llm_client):
        """When enable_metrics_endpoint is False, circuit_breaker_states returns None."""
        states = llm_client.circuit_breaker_states
        assert states is None

    def test_circuit_breaker_states_returns_dict_when_metrics_enabled(self, llm_client):
        """When enable_metrics_endpoint is True, circuit_breaker_states returns states dict."""
        # client.py imports: from core.config import cfg
        # Must patch the object as seen by client.py: core.llm_backend.client.cfg
        with patch("core.llm_backend.client.cfg") as mock_cfg:
            mock_cfg.enable_metrics_endpoint = True
            states = llm_client.circuit_breaker_states
            assert states is not None
            assert isinstance(states, dict)
            # Should have entries for each role
            assert "executor" in states
            assert "planner" in states
            assert states["executor"]["state"] == "closed"

    def test_tracer_error_on_breaker_metrics_failure(self, llm_client):
        """If tracer.step() raises, tracer.error() must log the failure."""
        with patch("core.llm_backend.client.tracer.step") as mock_step, \
             patch("core.llm_backend.client.tracer.error") as mock_error:
            mock_step.side_effect = RuntimeError("tracer failure")
            # Should not raise — errors are caught internally
            states = llm_client.circuit_breaker_states
            # tracer.error should have been called for the failed role
            assert mock_error.called, "tracer.error() was not called on tracer.step() failure"
