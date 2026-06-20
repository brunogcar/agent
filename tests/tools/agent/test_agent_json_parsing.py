"""Agent tool tests — JSON parsing for structured output roles."""
from __future__ import annotations

from unittest.mock import patch

from tools.agent import agent


class TestAgentJSONParsing:
    """Test JSON extraction for prompt-only JSON roles."""

    def test_json_role_parses_valid_json(self, mock_llm_result):
        mock_llm_result.text = (
            '{"workflow": "research", "tool": "web", "complexity": 5, "reason": "test"}'
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
        mock_llm_result.text = '```json\n{"verdict": "APPROVE"}\n```'
        mock_llm_result.parsed = None

        with patch("tools.agent.llm.complete", return_value=mock_llm_result):
            result = agent(role="review", task="Review this")

        assert result["parsed"]["verdict"] == "APPROVE"

    def test_api_json_role_uses_parsed_directly(self, mock_llm_result):
        """extract role uses API-level json_object — parsed already populated."""
        mock_llm_result.parsed = {"name": "Alice", "age": 30}
        mock_llm_result.text = '{"name": "Alice", "age": 30}'

        with patch("tools.agent.llm.complete") as mock_llm:
            mock_llm.return_value = mock_llm_result
            result = agent(role="extract", task="Extract person data")

            call_kwargs = mock_llm.call_args.kwargs
            assert call_kwargs["json_mode"] is True
            assert result["parsed"] == {"name": "Alice", "age": 30}
            assert "parse_warning" not in result

    def test_json_role_extracts_from_surrounding_text(self, mock_llm_result):
        mock_llm_result.text = 'Here is the result: {"verdict": "REVISE"} Thanks!'
        mock_llm_result.parsed = None

        with patch("tools.agent.llm.complete", return_value=mock_llm_result):
            result = agent(role="review", task="Review this")

        assert result["parsed"]["verdict"] == "REVISE"

    # ── Phase 3 additions: nested JSON regression tests ─────────────────────

    def test_json_role_parses_deeply_nested_json(self, mock_llm_result):
        """review role with nested issues array must parse correctly.

        Regression test for the old regex-based parser which used a non-greedy
        pattern and broke on nested objects by stopping at the first closing
        brace. The brace-counting parser correctly handles arbitrary depth.
        """
        mock_llm_result.text = (
            '{"verdict": "REVISE", "issues": ['
            ' {"severity": "critical", "description": "race condition"},'
            ' {"severity": "minor", "description": "typo"}'
            '], "corrected_patch": null}'
        )
        mock_llm_result.parsed = None

        with patch("tools.agent.llm.complete", return_value=mock_llm_result):
            result = agent(role="review", task="Review this patch")

        assert result["parsed"]["verdict"] == "REVISE"
        assert len(result["parsed"]["issues"]) == 2
        assert result["parsed"]["issues"][0]["severity"] == "critical"
        assert "parse_warning" not in result

    def test_json_role_parses_nested_plan_steps(self, mock_llm_result):
        """plan role with steps[].inputs nesting must parse correctly."""
        mock_llm_result.text = (
            '{"steps": ['
            ' {"step": 1, "tool": "web", "inputs": {"query": "python best practices"}},'
            ' {"step": 2, "tool": "python", "inputs": {"code": "print(1)"}}'
            ']}'
        )
        mock_llm_result.parsed = None

        with patch("tools.agent.llm.complete", return_value=mock_llm_result):
            result = agent(role="plan", task="Plan a research task")

        assert len(result["parsed"]["steps"]) == 2
        assert result["parsed"]["steps"][0]["inputs"]["query"] == "python best practices"
        assert "parse_warning" not in result

    def test_json_role_with_json_inside_string_value(self, mock_llm_result):
        """JSON containing string values with braces must not confuse parser."""
        mock_llm_result.text = (
            '{"analysis": "Use dict() not {} for empty dicts", "patch": "x = dict()"}'
        )
        mock_llm_result.parsed = None

        with patch("tools.agent.llm.complete", return_value=mock_llm_result):
            result = agent(role="code", task="Fix this code")

        assert result["parsed"]["analysis"] == "Use dict() not {} for empty dicts"
        assert result["parsed"]["patch"] == "x = dict()"
        assert "parse_warning" not in result

    def test_json_role_with_surrounding_text_and_nested_json(self, mock_llm_result):
        """LLM adds prose around nested JSON — brace parser must still extract it."""
        mock_llm_result.text = (
            "Here is my analysis of the code. I found several issues.\n\n"
            '{"verdict": "REVISE", "issues": [{"severity": "critical"}], "corrected_patch": "fix"}'
            "\n\nPlease let me know if you need anything else."
        )
        mock_llm_result.parsed = None

        with patch("tools.agent.llm.complete", return_value=mock_llm_result):
            result = agent(role="review", task="Review this")

        assert result["parsed"]["verdict"] == "REVISE"
        assert result["parsed"]["issues"][0]["severity"] == "critical"
        assert "parse_warning" not in result

    # ── Phase 4 additions: array-at-root and prose edge cases ───────────────

    def test_json_role_parses_array_at_root(self, mock_llm_result):
        """Array at root level is extracted and parsed correctly.

        Regression guard: old parser only looked for { and would silently
        extract the first inner object, discarding the rest.
        """
        mock_llm_result.text = '[{"step": 1}, {"step": 2}]'
        mock_llm_result.parsed = None

        with patch("tools.agent.llm.complete", return_value=mock_llm_result):
            result = agent(role="route", task="Route this")

        assert result["parsed"] == [{"step": 1}, {"step": 2}]
        assert "parse_warning" not in result

    def test_json_role_prose_with_braces_before_json(self, mock_llm_result):
        """Prose containing { before actual JSON must not mislead parser."""
        mock_llm_result.text = (
            "I analyzed the code. The function uses {} as a pattern.\n\n"
            '{"verdict": "REVISE", "issues": []}'
        )
        mock_llm_result.parsed = None

        with patch("tools.agent.llm.complete", return_value=mock_llm_result):
            result = agent(role="review", task="Review this")

        assert result["parsed"]["verdict"] == "REVISE"
        assert result["parsed"]["issues"] == []
        assert "parse_warning" not in result

    def test_extract_first_json_returns_none_for_no_json(self, mock_llm_result):
        """When no JSON markers exist, parsed is empty with warning."""
        mock_llm_result.text = "Just plain text with no JSON here."
        mock_llm_result.parsed = None

        with patch("tools.agent.llm.complete", return_value=mock_llm_result):
            result = agent(role="plan", task="Plan this")

        assert result["parsed"] == {}
        assert "parse_warning" in result
