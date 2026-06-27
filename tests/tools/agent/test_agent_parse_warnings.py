"""Agent tool tests — parse warning logging for JSON failures."""
from __future__ import annotations

from unittest.mock import patch

from tools.agent import agent
from tools.agent_core.parse_warnings import _get_parse_warnings, _clear_parse_warnings
from tools.agent_core.cache import _clear_cache


class TestParseWarningLogging:
    """Test that parse warnings are logged and retrievable."""

    def setup_method(self):
        _clear_parse_warnings()
        _clear_cache()

    def test_parse_warning_logged_on_failure(self, mock_llm_result):
        """When JSON parsing fails, a warning should be logged."""
        mock_llm_result.text = "not json"
        mock_llm_result.parsed = None

        with patch("tools.agent_core.actions.dispatch.llm.complete", return_value=mock_llm_result):
            agent(action="dispatch", role="route", task="test")

        warnings = _get_parse_warnings("route")
        assert len(warnings) == 1

    def test_parse_warning_not_logged_on_success(self, mock_llm_result):
        """Valid JSON should not produce a parse warning."""
        mock_llm_result.text = '{"key": "value"}'
        mock_llm_result.parsed = None

        with patch("tools.agent_core.actions.dispatch.llm.complete", return_value=mock_llm_result):
            agent(action="dispatch", role="route", task="test")

        warnings = _get_parse_warnings("route")
        assert len(warnings) == 0

    def test_parse_warning_log_max_size(self, mock_llm_result):
        """Log should not exceed max size."""
        mock_llm_result.text = "not json"
        mock_llm_result.parsed = None

        with patch("tools.agent_core.actions.dispatch.llm.complete", return_value=mock_llm_result):
            for _ in range(60):
                agent(action="dispatch", role="route", task="test")

        warnings = _get_parse_warnings("route")
        assert len(warnings) <= 50  # Max size

    def test_get_parse_warnings_filtered_by_role(self, mock_llm_result):
        """Warnings should be filterable by role."""
        mock_llm_result.text = "not json"
        mock_llm_result.parsed = None

        with patch("tools.agent_core.actions.dispatch.llm.complete", return_value=mock_llm_result):
            agent(action="dispatch", role="route", task="test")
            agent(action="dispatch", role="plan", task="test")

        route_warnings = _get_parse_warnings("route")
        plan_warnings = _get_parse_warnings("plan")
        assert len(route_warnings) == 1
        assert len(plan_warnings) == 1
