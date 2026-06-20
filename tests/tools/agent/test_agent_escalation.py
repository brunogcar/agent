"""Agent tool tests — autonomous model escalation on parse failure."""
from __future__ import annotations

from unittest.mock import patch, call

from tools.agent import agent


class TestModelEscalation:
    """Test auto-retry with planner model when JSON parsing fails."""

    def setup_method(self):
        from tools.agent import _CACHE
        _CACHE.clear()

    def test_escalation_triggered_on_parse_failure(self, mock_llm_result):
        """When primary model returns invalid JSON, planner model retries."""
        # First call: bad JSON
        bad_result = type("obj", (object,), {
            "ok": True, "text": "not json", "parsed": None,
            "model": "router", "elapsed": 1.0, "usage": {"prompt": 5, "completion": 5, "total": 10}
        })()
        # Escalation call: good JSON
        good_result = type("obj", (object,), {
            "ok": True, "text": '{"step": 1}', "parsed": None,
            "model": "planner", "elapsed": 2.0, "usage": {"prompt": 10, "completion": 10, "total": 20}
        })()

        with patch("tools.agent.llm.complete") as mock_llm:
            mock_llm.side_effect = [bad_result, good_result]
            result = agent(role="route", task="test")

        assert result["status"] == "success"
        assert result.get("escalated") is True
        assert result["parsed"] == {"step": 1}
        assert mock_llm.call_count == 2

    def test_no_escalation_when_json_valid(self, mock_llm_result):
        mock_llm_result.text = '{"step": 1}'
        mock_llm_result.parsed = None

        with patch("tools.agent.llm.complete", return_value=mock_llm_result) as mock_llm:
            result = agent(role="route", task="test")

        assert result["status"] == "success"
        assert "escalated" not in result
        assert mock_llm.call_count == 1

    def test_escalation_failure_keeps_parse_warning(self, mock_llm_result):
        """If escalation also fails, original parse_warning is preserved."""
        bad_result = type("obj", (object,), {
            "ok": True, "text": "still not json", "parsed": None,
            "model": "router", "elapsed": 1.0, "usage": {"prompt": 5, "completion": 5, "total": 10}
        })()
        worse_result = type("obj", (object,), {
            "ok": True, "text": "also bad", "parsed": None,
            "model": "planner", "elapsed": 2.0, "usage": {"prompt": 10, "completion": 10, "total": 20}
        })()

        with patch("tools.agent.llm.complete") as mock_llm:
            mock_llm.side_effect = [bad_result, worse_result]
            result = agent(role="route", task="test")

        assert result["status"] == "success"
        assert "parse_warning" in result
        assert "escalated" not in result
