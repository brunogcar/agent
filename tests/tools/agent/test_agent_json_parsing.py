"""Agent tool tests — JSON parsing fallback for prompt-only JSON roles."""
from __future__ import annotations

from unittest.mock import patch

from tools.agent import agent
from tools.agent_core.json_extract import _extract_first_json
from tools.agent_core.cache import _clear_cache


class TestAgentJSONParsing:
    """Test JSON parsing for roles that expect structured output."""

    def setup_method(self):
        _clear_cache()

    def test_json_role_parses_valid_json(self, mock_llm_result):
        mock_llm_result.text = '{"verdict": "APPROVE"}'

        with patch("tools.agent.llm.complete", return_value=mock_llm_result):
            result = agent(role="review", task="Review this")

        assert result["status"] == "success"
        assert result["parsed"]["verdict"] == "APPROVE"

    def test_json_role_handles_invalid_json_gracefully(self, mock_llm_result):
        mock_llm_result.text = "I think this looks good"

        with patch("tools.agent.llm.complete", return_value=mock_llm_result):
            result = agent(role="review", task="Review this")

        assert result["status"] == "success"
        assert result["parsed"] == {}
        assert "parse_warning" in result

    def test_json_role_strips_markdown_fences(self, mock_llm_result):
        mock_llm_result.text = '```json\n{"verdict": "APPROVE"}\n```'

        with patch("tools.agent.llm.complete", return_value=mock_llm_result):
            result = agent(role="review", task="Review this")

        assert result["parsed"]["verdict"] == "APPROVE"

    def test_api_json_role_uses_parsed_directly(self, mock_llm_result):
        """extract role with API json_mode should use result.parsed directly."""
        mock_llm_result.parsed = {"name": "test"}
        mock_llm_result.text = '{"name": "test"}'

        with patch("tools.agent.llm.complete", return_value=mock_llm_result):
            result = agent(role="extract", task="Extract name")

        assert result["parsed"]["name"] == "test"

    def test_json_role_extracts_from_surrounding_text(self, mock_llm_result):
        mock_llm_result.text = 'Here is the result: \n{"verdict": "APPROVE"}\nDone!'

        with patch("tools.agent.llm.complete", return_value=mock_llm_result):
            result = agent(role="review", task="Review this")

        assert result["parsed"]["verdict"] == "APPROVE"

    def test_json_role_parses_deeply_nested_json(self, mock_llm_result):
        mock_llm_result.text = '{"a": {"b": {"c": 1}}}'

        with patch("tools.agent.llm.complete", return_value=mock_llm_result):
            result = agent(role="plan", task="test")

        assert result["parsed"]["a"]["b"]["c"] == 1

    def test_json_role_parses_nested_plan_steps(self, mock_llm_result):
        mock_llm_result.text = '{"steps": [{"action": "search"}, {"action": "summarize"}]}'

        with patch("tools.agent.llm.complete", return_value=mock_llm_result):
            result = agent(role="plan", task="Plan research")

        assert len(result["parsed"]["steps"]) == 2

    def test_json_role_with_json_inside_string_value(self, mock_llm_result):
        mock_llm_result.text = '{"code": "{\\"a\\": 1}"}'

        with patch("tools.agent.llm.complete", return_value=mock_llm_result):
            result = agent(role="code", task="test")

        assert result["parsed"]["code"] == '{"a": 1}'

    def test_json_role_with_surrounding_text_and_nested_json(self, mock_llm_result):
        mock_llm_result.text = 'Analysis complete. \n{"analysis": "complex", "nested": {"value": 42}}\nEnd.'

        with patch("tools.agent.llm.complete", return_value=mock_llm_result):
            result = agent(role="code", task="test")

        assert result["parsed"]["nested"]["value"] == 42

    def test_json_role_parses_array_at_root(self, mock_llm_result):
        mock_llm_result.text = '[{"step": 1}, {"step": 2}]'

        with patch("tools.agent.llm.complete", return_value=mock_llm_result):
            result = agent(role="plan", task="test")

        assert len(result["parsed"]) == 2

    def test_json_role_prose_with_braces_before_json(self, mock_llm_result):
        mock_llm_result.text = 'Some {prose} before \n{"real": "json"}'

        with patch("tools.agent.llm.complete", return_value=mock_llm_result):
            result = agent(role="plan", task="test")

        assert result["parsed"]["real"] == "json"

    def test_extract_first_json_returns_none_for_no_json(self):
        assert _extract_first_json("no json here") is None
