"""Agent tool tests — structured error taxonomy."""
from __future__ import annotations

from unittest.mock import patch

from tools.agent import agent
from tools.agent_core.cache import _clear_cache


class TestAgentErrorTaxonomy:
    """Test error_code field in error responses."""

    def setup_method(self):
        """Clear response cache between tests for cacheable roles."""
        _clear_cache()

    def test_unknown_role_returns_invalid_role(self):
        result = agent(role="banana", task="test")
        assert result["status"] == "error"
        assert result["error_code"] == "INVALID_ROLE"

    def test_empty_task_returns_invalid_input(self):
        result = agent(role="classify", task="")
        assert result["status"] == "error"
        assert result["error_code"] == "INVALID_INPUT"

    def test_llm_timeout_returns_timeout(self, mock_llm_result):
        mock_llm_result.ok = False
        mock_llm_result.error = "Executor model timed out after 120s"

        with patch("tools.agent.llm.complete", return_value=mock_llm_result):
            result = agent(role="code", task="Fix bug")

        assert result["status"] == "error"
        assert result["error_code"] == "TIMEOUT"

    def test_llm_circuit_breaker_returns_circuit_open(self, mock_llm_result):
        mock_llm_result.ok = False
        mock_llm_result.error = "Circuit breaker is OPEN for role code"

        with patch("tools.agent.llm.complete", return_value=mock_llm_result):
            result = agent(role="code", task="Fix bug")

        assert result["status"] == "error"
        assert result["error_code"] == "CIRCUIT_OPEN"

    def test_llm_rate_limit_returns_rate_limit(self, mock_llm_result):
        mock_llm_result.ok = False
        mock_llm_result.error = "Rate limit exceeded for model"

        with patch("tools.agent.llm.complete", return_value=mock_llm_result):
            result = agent(role="research", task="Find docs")

        assert result["status"] == "error"
        assert result["error_code"] == "RATE_LIMIT"

    def test_generic_llm_error_returns_model_error(self, mock_llm_result):
        mock_llm_result.ok = False
        mock_llm_result.error = "Something went wrong"

        with patch("tools.agent.llm.complete", return_value=mock_llm_result):
            result = agent(role="plan", task="Plan this")

        assert result["status"] == "error"
        assert result["error_code"] == "MODEL_ERROR"

    def test_error_response_includes_all_fields(self, mock_llm_result):
        mock_llm_result.ok = False
        mock_llm_result.error = "Timeout"
        mock_llm_result.elapsed = 60.0
        mock_llm_result.model = "test-model"

        with patch("tools.agent.llm.complete", return_value=mock_llm_result):
            result = agent(role="classify", task="test")

        assert "error_code" in result
        assert "role" in result
        assert "error" in result
        assert "elapsed" in result
        assert "model" in result
