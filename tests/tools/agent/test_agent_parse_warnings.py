"""Agent tool tests — parse warning logging and retrieval tests."""
from __future__ import annotations

from unittest.mock import patch

from tools.agent import agent
from tools.agent_core.cache import _clear_cache
from tools.agent_core.parse_warnings import (
    _log_parse_warning,
    _get_parse_warnings,
    _clear_parse_warnings,
)


class TestParseWarningLogging:
    """Test parse warning log behavior."""

    def setup_method(self):
        _clear_cache()
        _clear_parse_warnings()

    def test_log_parse_warning_appends(self):
        """Logging a warning appends to the rolling log."""
        _log_parse_warning("plan", "bad json", "raw text here")
        warnings = _get_parse_warnings()
        assert len(warnings) == 1
        assert warnings[0]["role"] == "plan"
        assert "bad json" in warnings[0]["warning"]

    def test_log_parse_warning_truncates_preview(self):
        """text_preview is truncated to 200 chars."""
        long_text = "x" * 500
        _log_parse_warning("code", "error", long_text)
        warnings = _get_parse_warnings()
        assert len(warnings[0]["text_preview"]) <= 200

    def test_log_parse_warning_rolls_at_max(self):
        """Log trims to max 50 entries via pop(0)."""
        for i in range(55):
            _log_parse_warning("route", f"warning {i}", "text")
        warnings = _get_parse_warnings()
        assert len(warnings) == 50
        # Oldest entry should be warning 5 (first 5 popped)
        assert "warning 5" in warnings[0]["warning"]

    def test_get_parse_warnings_filtered_by_role(self):
        """Filtering by role returns only matching warnings."""
        _log_parse_warning("plan", "plan warning", "plan text")
        _log_parse_warning("code", "code warning", "code text")

        plan_warnings = _get_parse_warnings("plan")
        assert len(plan_warnings) == 1
        assert plan_warnings[0]["role"] == "plan"

        code_warnings = _get_parse_warnings("code")
        assert len(code_warnings) == 1
        assert code_warnings[0]["role"] == "code"

    def test_clear_parse_warnings(self):
        """Clearing removes all warnings."""
        _log_parse_warning("plan", "warning", "text")
        _clear_parse_warnings()
        assert _get_parse_warnings() == []


class TestParseWarningIntegration:
    """Parse warnings triggered via agent() dispatch path."""

    def setup_method(self):
        _clear_cache()
        _clear_parse_warnings()

    def test_parse_warning_logged_on_json_failure(self, mock_llm_result):
        """When a JSON role returns invalid JSON, a parse warning is logged."""
        mock_llm_result.text = "not valid json"
        mock_llm_result.parsed = None

        with patch("tools.agent_core.actions.dispatch.llm.complete", return_value=mock_llm_result):
            agent(action="dispatch", role="route", task="test")

        warnings = _get_parse_warnings("route")
        assert len(warnings) == 1
        assert "route" in warnings[0]["warning"]

    def test_no_parse_warning_on_valid_json(self, mock_llm_result):
        """Valid JSON should not produce a parse warning."""
        mock_llm_result.text = '{"workflow": "research"}'
        mock_llm_result.parsed = None

        with patch("tools.agent_core.actions.dispatch.llm.complete", return_value=mock_llm_result):
            agent(action="dispatch", role="route", task="test")

        assert _get_parse_warnings("route") == []
