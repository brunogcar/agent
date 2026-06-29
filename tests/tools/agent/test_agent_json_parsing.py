"""Agent tool tests — JSON parsing fallback for prompt-only JSON roles."""
from __future__ import annotations

from unittest.mock import patch

from tools.agent import agent
from tools.agent_ops.cache import _clear_cache


class TestAgentJSONParsing:
    """Test JSON parsing for roles that expect structured output."""

    def setup_method(self):
        _clear_cache()

    def test_json_role_parses_valid_json(self, mock_llm_result):
        mock_llm_result.text = '{"workflow": "research", "tool": "web"}'
        mock_llm_result.parsed = None

        with patch("tools.agent_ops.actions.dispatch.llm.complete", return_value=mock_llm_result):
            result = agent(action="dispatch", role="route", task="test")
            assert result["status"] == "success"
            assert "parsed" in result
            assert result["parsed"]["workflow"] == "research"

    def test_json_role_handles_invalid_json_gracefully(self, mock_llm_result):
        mock_llm_result.text = "not json at all"
        mock_llm_result.parsed = None

        with patch("tools.agent_ops.actions.dispatch.llm.complete", return_value=mock_llm_result):
            result = agent(action="dispatch", role="route", task="test")
            assert result["status"] == "success"
            assert "parsed" in result
            assert result["parsed"] == {}
            assert "parse_warning" in result

    def test_json_role_strips_markdown_fences(self, mock_llm_result):
        mock_llm_result.text = "```json\n{\"key\": \"value\"}\n```"
        mock_llm_result.parsed = None

        with patch("tools.agent_ops.actions.dispatch.llm.complete", return_value=mock_llm_result):
            result = agent(action="dispatch", role="route", task="test")
            assert result["status"] == "success"
            assert result["parsed"]["key"] == "value"

    def test_api_json_role_uses_parsed_directly(self, mock_llm_result):
        """extract role with API json_mode should use result.parsed directly."""
        mock_llm_result.parsed = {"field": "value"}

        with patch("tools.agent_ops.actions.dispatch.llm.complete", return_value=mock_llm_result):
            result = agent(action="dispatch", role="extract", task="test")
            assert result["status"] == "success"
            assert result["parsed"]["field"] == "value"

    def test_json_role_extracts_from_surrounding_text(self, mock_llm_result):
        mock_llm_result.text = 'Some text before {"key": "value"} and after'
        mock_llm_result.parsed = None

        with patch("tools.agent_ops.actions.dispatch.llm.complete", return_value=mock_llm_result):
            result = agent(action="dispatch", role="route", task="test")
            assert result["status"] == "success"
            assert result["parsed"]["key"] == "value"

    def test_json_role_parses_deeply_nested_json(self, mock_llm_result):
        mock_llm_result.text = '{"a": {"b": {"c": {"d": "deep"}}}}'
        mock_llm_result.parsed = None

        with patch("tools.agent_ops.actions.dispatch.llm.complete", return_value=mock_llm_result):
            result = agent(action="dispatch", role="route", task="test")
            assert result["parsed"]["a"]["b"]["c"]["d"] == "deep"

    def test_json_role_parses_nested_plan_steps(self, mock_llm_result):
        mock_llm_result.text = '{"steps": [{"step": 1, "action": "web"}, {"step": 2, "action": "python"}]}'
        mock_llm_result.parsed = None

        with patch("tools.agent_ops.actions.dispatch.llm.complete", return_value=mock_llm_result):
            result = agent(action="dispatch", role="plan", task="test")
            assert len(result["parsed"]["steps"]) == 2

    def test_json_role_with_code_string_value(self, mock_llm_result):
        """JSON containing a code string with escaped newlines."""
        mock_llm_result.text = '{"code": "def foo():\\n    return 1"}'
        mock_llm_result.parsed = None

        with patch("tools.agent_ops.actions.dispatch.llm.complete", return_value=mock_llm_result):
            result = agent(action="dispatch", role="code", task="test")
            assert result["status"] == "success"
            assert "def foo()" in result["parsed"]["code"]

    def test_json_role_with_surrounding_text_and_nested_json(self, mock_llm_result):
        mock_llm_result.text = 'Here is the result: {"data": {"items": [1, 2, 3]}} Thanks!'
        mock_llm_result.parsed = None

        with patch("tools.agent_ops.actions.dispatch.llm.complete", return_value=mock_llm_result):
            result = agent(action="dispatch", role="route", task="test")
            assert result["parsed"]["data"]["items"] == [1, 2, 3]

    def test_json_role_parses_array_at_root(self, mock_llm_result):
        mock_llm_result.text = '[{"id": 1}, {"id": 2}]'
        mock_llm_result.parsed = None

        with patch("tools.agent_ops.actions.dispatch.llm.complete", return_value=mock_llm_result):
            result = agent(action="dispatch", role="route", task="test")
            assert len(result["parsed"]) == 2

    def test_json_role_prose_with_braces_before_json(self, mock_llm_result):
        mock_llm_result.text = 'Here {is} some text {"key": "value"}'
        mock_llm_result.parsed = None

        with patch("tools.agent_ops.actions.dispatch.llm.complete", return_value=mock_llm_result):
            result = agent(action="dispatch", role="route", task="test")
            assert result["parsed"]["key"] == "value"

    def test_extract_first_json_returns_none_for_no_json(self):
        from tools.agent_ops.json_extract import _extract_first_json
        assert _extract_first_json("no json here") is None
        assert _extract_first_json("{invalid") is None
