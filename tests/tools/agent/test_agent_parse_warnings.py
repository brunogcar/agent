"""Agent tool tests — parse warning logging for JSON failures."""
from __future__ import annotations

from unittest.mock import patch

from tools.agent import agent
from tools.agent_core.parse_warnings import _get_parse_warnings, _clear_parse_warnings


class TestParseWarningLogging:
    """Test that parse warnings are logged and retrievable."""

    def setup_method(self):
        from tools.agent_core.cache import _clear_cache
        from tools.agent_core.metrics import _clear_metrics
        _clear_cache()
        _clear_metrics()
        _clear_parse_warnings()

    def test_parse_warning_logged_on_failure(self, mock_llm_result):
        """When JSON parsing fails, a warning should be logged."""
        mock_llm_result.text = "not json"

        with patch("tools.agent.llm.complete", return_value=mock_llm_result):
            agent(role="route", task="test")

        warnings = _get_parse_warnings("route")
        assert len(warnings) == 1
        assert "not valid JSON" in warnings[0]["warning"]

    def test_parse_warning_not_logged_on_success(self, mock_llm_result):
        """Valid JSON should not produce a parse warning."""
        mock_llm_result.text = '{"step": 1}'

        with patch("tools.agent.llm.complete", return_value=mock_llm_result):
            agent(role="route", task="test")

        warnings = _get_parse_warnings("route")
        assert len(warnings) == 0

    def test_parse_warning_log_max_size(self, mock_llm_result):
        """Log should not exceed max size."""
        mock_llm_result.text = "not json"

        with patch("tools.agent.llm.complete", return_value=mock_llm_result):
            for i in range(60):
                agent(role="route", task=f"test {i}")

        warnings = _get_parse_warnings("route")
        assert len(warnings) <= 50

    def test_get_parse_warnings_filtered_by_role(self, mock_llm_result):
        """Warnings should be filterable by role."""
        mock_llm_result.text = "not json"

        with patch("tools.agent.llm.complete", return_value=mock_llm_result):
            agent(role="route", task="test1")
            agent(role="plan", task="test2")

        route_warnings = _get_parse_warnings("route")
        plan_warnings = _get_parse_warnings("plan")
        assert len(route_warnings) == 1
        assert len(plan_warnings) == 1
