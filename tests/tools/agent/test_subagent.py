"""Tests for agent subagent action."""
from __future__ import annotations

from unittest.mock import patch, MagicMock

from tools.agent import agent


class TestSubagentDispatch:
    """Subagent dispatches a fresh LLM call with curated context."""

    def test_subagent_success(self):
        """Mock LLM returns text — facade should return success."""
        mock_result = MagicMock()
        mock_result.ok = True
        mock_result.text = "The bug is on line 42."
        mock_result.model = "test-model"
        mock_result.usage = {"total": 100}
        mock_result.parsed = None

        with patch("tools.agent_ops.actions.subagent.llm.complete", return_value=mock_result):
            result = agent(
                action="subagent",
                role="executor",
                task="Find the bug",
                context="def foo(): pass",
            )

        assert result["status"] == "success"
        assert result["role"] == "executor"
        assert result["response"] == "The bug is on line 42."
        assert result["model"] == "test-model"
        assert "elapsed" in result

    def test_subagent_missing_task(self):
        """Missing task → fail() before any LLM call."""
        with patch("tools.agent_ops.actions.subagent.llm.complete") as mock_complete:
            result = agent(action="subagent", role="executor")

        assert result["status"] == "error"
        assert "task is required" in result["error"]
        mock_complete.assert_not_called()

    def test_subagent_default_system_prompt(self):
        """Empty system param → uses minimal default."""
        mock_result = MagicMock()
        mock_result.ok = True
        mock_result.text = "Done"
        mock_result.model = "test"
        mock_result.usage = {}
        mock_result.parsed = None

        with patch("tools.agent_ops.actions.subagent.llm.complete", return_value=mock_result) as mock_complete:
            agent(action="subagent", role="executor", task="Do something")

        call_kwargs = mock_complete.call_args.kwargs
        assert "focused assistant" in call_kwargs["system"]

    def test_subagent_custom_system_prompt(self):
        """Caller provides system prompt → passed through to LLM."""
        mock_result = MagicMock()
        mock_result.ok = True
        mock_result.text = "Done"
        mock_result.model = "test"
        mock_result.usage = {}
        mock_result.parsed = None

        with patch("tools.agent_ops.actions.subagent.llm.complete", return_value=mock_result) as mock_complete:
            agent(
                action="subagent",
                role="planner",
                task="Plan the work",
                system="You are a senior architect.",
            )

        call_kwargs = mock_complete.call_args.kwargs
        assert call_kwargs["system"] == "You are a senior architect."

    def test_subagent_context_passed_through(self):
        """Curated context is passed to the LLM call."""
        mock_result = MagicMock()
        mock_result.ok = True
        mock_result.text = "Done"
        mock_result.model = "test"
        mock_result.usage = {}
        mock_result.parsed = None

        with patch("tools.agent_ops.actions.subagent.llm.complete", return_value=mock_result) as mock_complete:
            agent(
                action="subagent",
                role="executor",
                task="Review this",
                context="def foo(): return 42",
            )

        call_kwargs = mock_complete.call_args.kwargs
        assert call_kwargs["context"] == "def foo(): return 42"

    def test_subagent_llm_error(self):
        """LLM returns error → facade returns error with error_code."""
        mock_result = MagicMock()
        mock_result.ok = False
        mock_result.error = "Model timed out"
        mock_result.model = "test"
        mock_result.usage = {}

        with patch("tools.agent_ops.actions.subagent.llm.complete", return_value=mock_result):
            result = agent(action="subagent", role="executor", task="Do something")

        assert result["status"] == "error"
        assert result["error_code"] == "TIMEOUT"
        assert "timed out" in result["error"].lower()

    def test_subagent_json_schema_string_parsed(self):
        """json_schema passed as JSON string → parsed to dict."""
        mock_result = MagicMock()
        mock_result.ok = True
        mock_result.text = '{"issues": []}'
        mock_result.model = "test"
        mock_result.usage = {}
        mock_result.parsed = {"issues": []}

        schema_str = '{"type":"object","properties":{"issues":{"type":"array"}}}'

        with patch("tools.agent_ops.actions.subagent.llm.complete", return_value=mock_result) as mock_complete:
            result = agent(
                action="subagent",
                role="executor",
                task="Review code",
                json_schema=schema_str,
            )

        call_kwargs = mock_complete.call_args.kwargs
        assert call_kwargs["json_schema"] == {"type": "object", "properties": {"issues": {"type": "array"}}}
        assert result["status"] == "success"
        assert result["parsed"] == {"issues": []}

    def test_subagent_invalid_json_schema(self):
        """Invalid json_schema string → error."""
        with patch("tools.agent_ops.actions.subagent.llm.complete") as mock_complete:
            result = agent(
                action="subagent",
                role="executor",
                task="Do something",
                json_schema="{not valid json}",
            )

        assert result["status"] == "error"
        assert "json_schema must be valid JSON" in result["error"]
        mock_complete.assert_not_called()

    def test_subagent_role_defaults_to_executor(self):
        """Empty role → defaults to 'executor'."""
        mock_result = MagicMock()
        mock_result.ok = True
        mock_result.text = "Done"
        mock_result.model = "test"
        mock_result.usage = {}
        mock_result.parsed = None

        with patch("tools.agent_ops.actions.subagent.llm.complete", return_value=mock_result) as mock_complete:
            agent(action="subagent", task="Do something")

        call_kwargs = mock_complete.call_args.kwargs
        assert call_kwargs["role"] == "executor"

    def test_subagent_temperature_and_max_tokens(self):
        """temperature + max_tokens passed through when >= 0 / > 0."""
        mock_result = MagicMock()
        mock_result.ok = True
        mock_result.text = "Done"
        mock_result.model = "test"
        mock_result.usage = {}
        mock_result.parsed = None

        with patch("tools.agent_ops.actions.subagent.llm.complete", return_value=mock_result) as mock_complete:
            agent(
                action="subagent",
                role="executor",
                task="Be creative",
                temperature=0.7,
                max_tokens=500,
            )

        call_kwargs = mock_complete.call_args.kwargs
        assert call_kwargs["temperature"] == 0.7
        assert call_kwargs["max_tokens"] == 500
