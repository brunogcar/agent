"""Agent tool tests — structured parse_warning logging."""
from __future__ import annotations

from unittest.mock import patch

from tools.agent import agent, _get_parse_warnings, _clear_parse_warnings


class TestParseWarningLogging:
    """Test parse warning logging for data-driven prompt tuning."""

    def setup_method(self):
        from tools.agent import _CACHE
        _CACHE.clear()
        _clear_parse_warnings()

    def test_parse_warning_logged_on_failure(self, mock_llm_result):
        mock_llm_result.text = "not json at all"
        mock_llm_result.parsed = None

        with patch("tools.agent.llm.complete", return_value=mock_llm_result):
            agent(role="plan", task="test")

        warnings = _get_parse_warnings("plan")
        assert len(warnings) == 1
        assert "plan" in warnings[0]["warning"]

    def test_parse_warning_not_logged_on_success(self, mock_llm_result):
        mock_llm_result.text = '{"step": 1}'
        mock_llm_result.parsed = None

        with patch("tools.agent.llm.complete", return_value=mock_llm_result):
            agent(role="plan", task="test")

        warnings = _get_parse_warnings("plan")
        assert len(warnings) == 0

    def test_parse_warning_log_max_size(self, mock_llm_result):
        """Log should not grow unbounded."""
        mock_llm_result.text = "bad"
        mock_llm_result.parsed = None

        with patch("tools.agent.llm.complete", return_value=mock_llm_result):
            for i in range(60):
                agent(role="plan", task=f"test{i}")

        all_warnings = _get_parse_warnings()
        assert len(all_warnings) <= 50  # _PARSE_WARNING_LOG_MAX

    def test_get_parse_warnings_filtered_by_role(self, mock_llm_result):
        mock_llm_result.text = "bad"
        mock_llm_result.parsed = None

        with patch("tools.agent.llm.complete", return_value=mock_llm_result):
            agent(role="plan", task="test1")
            agent(role="route", task="test2")

        plan_warnings = _get_parse_warnings("plan")
        route_warnings = _get_parse_warnings("route")
        assert len(plan_warnings) == 1
        assert len(route_warnings) == 1
