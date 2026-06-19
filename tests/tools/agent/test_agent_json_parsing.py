"""Agent tool tests — JSON parsing for structured output roles."""
from __future__ import annotations

from unittest.mock import patch

from tools.agent import agent


class TestAgentJSONParsing:
    """Test JSON extraction for prompt-only JSON roles."""

    def test_json_role_parses_valid_json(self, mock_llm_result):
        mock_llm_result.text = (
            '{\"workflow\": \"research\", \"tool\": \"web\", \"complexity\": 5, \"reason\": \"test\"}'
        )
        mock_llm_result.parsed = None  # Simulate prompt-only JSON parsing

        with patch("tools.agent.llm.complete", return_value=mock_llm_result):
            result = agent(role="route", task="Search the web")

        assert result["status"] == "success"
        assert "parsed" in result
        assert result["parsed"]["workflow"] == "research"

    def test_json_role_handles_invalid_json_gracefully(self, mock_llm_result):
        mock_llm_result.text = "I cannot output JSON, here is my thought process..."
        mock_llm_result.parsed = None

        with patch("tools.agent.llm.complete", return_value=mock_llm_result):
            result = agent(role="plan", task="Plan this")

        assert result["status"] == "success"
        assert result["parsed"] == {}
        assert "parse_warning" in result

    def test_json_role_strips_markdown_fences(self, mock_llm_result):
        mock_llm_result.text = '```json\n{\"verdict\": \"APPROVE\"}\n```'
        mock_llm_result.parsed = None

        with patch("tools.agent.llm.complete", return_value=mock_llm_result):
            result = agent(role="review", task="Review this")

        assert result["parsed"]["verdict"] == "APPROVE"

    def test_api_json_role_uses_parsed_directly(self, mock_llm_result):
        """extract role uses API-level json_object — parsed already populated."""
        mock_llm_result.parsed = {"name": "Alice", "age": 30}
        mock_llm_result.text = '{\"name\": \"Alice\", \"age\": 30}'

        with patch("tools.agent.llm.complete") as mock_llm:
            mock_llm.return_value = mock_llm_result
            result = agent(role="extract", task="Extract person data")

        call_kwargs = mock_llm.call_args.kwargs
        assert call_kwargs["json_mode"] is True
        assert result["parsed"] == {"name": "Alice", "age": 30}
        assert "parse_warning" not in result

    def test_json_role_extracts_from_surrounding_text(self, mock_llm_result):
        mock_llm_result.text = 'Here is the result: {\"verdict\": \"REVISE\"} Thanks!'
        mock_llm_result.parsed = None

        with patch("tools.agent.llm.complete", return_value=mock_llm_result):
            result = agent(role="review", task="Review this")

        assert result["parsed"]["verdict"] == "REVISE"
