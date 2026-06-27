"""Agent tool tests — autonomous model escalation on parse failure."""
from __future__ import annotations

from unittest.mock import patch

from tools.agent import agent
from tools.agent_core.cache import _clear_cache


class TestModelEscalation:
    """Test auto-retry with planner model when JSON parsing fails."""

    def setup_method(self):
        _clear_cache()

    def test_escalation_triggered_on_parse_failure(self, mock_llm_result):
        """When primary model returns invalid JSON, planner model retries."""
        mock_llm_result.text = "not valid json"
        mock_llm_result.parsed = None

        escalation_result = type(mock_llm_result)()
        escalation_result.ok = True
        escalation_result.text = '{"valid": true}'
        escalation_result.parsed = None
        escalation_result.model = "planner"
        escalation_result.usage = {"total": 20}

        with patch("tools.agent_core.actions.dispatch.llm.complete") as mock_llm:
            mock_llm.side_effect = [mock_llm_result, escalation_result]
            result = agent(action="dispatch", role="route", task="test")

            assert result["status"] == "success"
            assert "parsed" in result
            assert result.get("escalated") is True
            assert mock_llm.call_count == 2

    def test_no_escalation_when_json_valid(self, mock_llm_result):
        mock_llm_result.text = '{"workflow": "research"}'
        mock_llm_result.parsed = None

        with patch("tools.agent_core.actions.dispatch.llm.complete", return_value=mock_llm_result) as mock_llm:
            result = agent(action="dispatch", role="route", task="test")
            assert result["status"] == "success"
            assert "parsed" in result
            assert mock_llm.call_count == 1

    def test_escalation_failure_keeps_parse_warning(self, mock_llm_result):
        """If escalation also fails, original parse_warning is preserved."""
        mock_llm_result.text = "not valid json"
        mock_llm_result.parsed = None

        escalation_result = type(mock_llm_result)()
        escalation_result.ok = True
        escalation_result.text = "also not json"
        escalation_result.parsed = None
        escalation_result.model = "planner"
        escalation_result.usage = {"total": 20}

        with patch("tools.agent_core.actions.dispatch.llm.complete") as mock_llm:
            mock_llm.side_effect = [mock_llm_result, escalation_result]
            result = agent(action="dispatch", role="route", task="test")

            assert result["status"] == "success"
            assert "parse_warning" in result
