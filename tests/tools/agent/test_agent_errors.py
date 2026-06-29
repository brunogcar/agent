"""Agent tool tests — structured error taxonomy."""
from __future__ import annotations

from unittest.mock import patch

from tools.agent import agent
from tools.agent_ops.cache import _clear_cache


class TestAgentErrorTaxonomy:
    """Test error_code field in error responses."""

    def setup_method(self):
        _clear_cache()

    def test_unknown_action_returns_error(self):
        result = agent(action="nonexistent", role="classify", task="test")
        assert result["status"] == "error"
        assert "Unknown action" in result["error"]

    def test_unknown_role_returns_invalid_role(self):
        result = agent(action="dispatch", role="unknown_role", task="do something")
        assert result["status"] == "error"
        assert result["error_code"] == "INVALID_ROLE"

    def test_empty_task_returns_invalid_input(self):
        result = agent(action="dispatch", role="classify", task="")
        assert result["status"] == "error"
        assert result["error_code"] == "INVALID_INPUT"

    def test_llm_timeout_returns_timeout(self, mock_llm_result):
        mock_llm_result.ok = False
        mock_llm_result.error = "Request timed out after 30s"

        with patch("tools.agent_ops.actions.dispatch.llm.complete", return_value=mock_llm_result):
            result = agent(action="dispatch", role="classify", task="test")
            assert result["error_code"] == "TIMEOUT"

    def test_llm_circuit_breaker_returns_circuit_open(self, mock_llm_result):
        mock_llm_result.ok = False
        mock_llm_result.error = "Circuit breaker is open"

        with patch("tools.agent_ops.actions.dispatch.llm.complete", return_value=mock_llm_result):
            result = agent(action="dispatch", role="classify", task="test")
            assert result["error_code"] == "CIRCUIT_OPEN"

    def test_llm_rate_limit_returns_rate_limit(self, mock_llm_result):
        mock_llm_result.ok = False
        mock_llm_result.error = "Rate limit exceeded"

        with patch("tools.agent_ops.actions.dispatch.llm.complete", return_value=mock_llm_result):
            result = agent(action="dispatch", role="classify", task="test")
            assert result["error_code"] == "RATE_LIMIT"

    def test_generic_llm_error_returns_model_error(self, mock_llm_result):
        mock_llm_result.ok = False
        mock_llm_result.error = "Some random error"

        with patch("tools.agent_ops.actions.dispatch.llm.complete", return_value=mock_llm_result):
            result = agent(action="dispatch", role="classify", task="test")
            assert result["error_code"] == "MODEL_ERROR"

    def test_error_response_includes_all_fields(self, mock_llm_result):
        mock_llm_result.ok = False
        mock_llm_result.error = "Test error"

        with patch("tools.agent_ops.actions.dispatch.llm.complete", return_value=mock_llm_result):
            result = agent(action="dispatch", role="classify", task="test")
            assert "status" in result
            assert "error_code" in result
            assert "role" in result
            assert "error" in result
            assert "elapsed" in result
            assert "model" in result
