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
        assert "focused subagent" in call_kwargs["system"]

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


class TestSubagentMultiTurn:
    """[v2.0] Multi-turn ReAct loop tests."""

    def test_multi_turn_final_answer_on_turn_1(self):
        """LLM returns final_answer immediately — 1 turn, no tool calls."""
        mock_result = MagicMock()
        mock_result.ok = True
        mock_result.model = "test"
        mock_result.usage = {"total": 50}
        mock_result.parsed = {"thought": "I know the answer", "final_answer": "The bug is on line 42"}
        mock_result.text = '{"thought": "I know", "final_answer": "The bug is on line 42"}'

        with patch("tools.agent_ops.actions.subagent.llm.complete", return_value=mock_result):
            result = agent(
                action="subagent",
                role="executor",
                task="Find the bug",
                tools="file,git",
            )

        assert result["status"] == "success"
        assert result["response"] == "The bug is on line 42"
        assert result["turns"] == 1

    def test_multi_turn_tool_call_then_final_answer(self):
        """LLM calls a tool on turn 1, then gives final answer on turn 2."""
        # Turn 1: tool call
        turn1 = MagicMock()
        turn1.ok = True
        turn1.model = "test"
        turn1.usage = {"total": 100}
        turn1.parsed = {"thought": "Need to read file", "tool_call": {"name": "file", "arguments": {"action": "read", "path": "test.py"}}}
        turn1.text = '{"thought": "Need to read file", "tool_call": {"name": "file", "arguments": {"action": "read", "path": "test.py"}}}'

        # Turn 2: final answer
        turn2 = MagicMock()
        turn2.ok = True
        turn2.model = "test"
        turn2.usage = {"total": 80}
        turn2.parsed = {"thought": "Found it", "final_answer": "Bug is a missing import"}
        turn2.text = '{"thought": "Found it", "final_answer": "Bug is a missing import"}'

        with patch("tools.agent_ops.actions.subagent.llm.complete", side_effect=[turn1, turn2]):
            with patch("tools.agent_ops.actions.subagent._execute_tool", return_value="file content here"):
                result = agent(
                    action="subagent",
                    role="executor",
                    task="Find the bug",
                    tools="file",
                    max_turns=5,
                )

        assert result["status"] == "success"
        assert result["response"] == "Bug is a missing import"
        assert result["turns"] == 2

    def test_multi_turn_max_turns_exceeded(self):
        """LLM keeps calling tools — hits max_turns limit."""
        mock_result = MagicMock()
        mock_result.ok = True
        mock_result.model = "test"
        mock_result.usage = {"total": 100}
        mock_result.parsed = {"thought": "Checking", "tool_call": {"name": "file", "arguments": {"action": "read", "path": "test.py"}}}
        mock_result.text = '{"thought": "Checking", "tool_call": {"name": "file", "arguments": {"action": "read", "path": "test.py"}}}'

        with patch("tools.agent_ops.actions.subagent.llm.complete", return_value=mock_result):
            with patch("tools.agent_ops.actions.subagent._execute_tool", return_value="file content"):
                result = agent(
                    action="subagent",
                    role="executor",
                    task="Keep checking",
                    tools="file",
                    max_turns=3,
                )

        assert result["status"] == "max_turns"
        assert result["turns"] == 3

    def test_multi_turn_disallowed_tool_rejected(self):
        """Caller requests a tool not in the allowlist — error before any LLM call."""
        with patch("tools.agent_ops.actions.subagent.llm.complete") as mock_complete:
            result = agent(
                action="subagent",
                role="executor",
                task="Do something",
                tools="github,agent",  # not in _ALLOWED_SUBAGENT_TOOLS
            )

        assert result["status"] == "error"
        assert "not allowed for subagents" in result["error"]
        mock_complete.assert_not_called()

    def test_multi_turn_consecutive_tool_failures_bail(self):
        """3 consecutive tool failures → bail with TOOL_FAILURES error."""
        mock_result = MagicMock()
        mock_result.ok = True
        mock_result.model = "test"
        mock_result.usage = {"total": 100}
        mock_result.parsed = {"thought": "Trying", "tool_call": {"name": "file", "arguments": {"action": "read", "path": "missing.py"}}}
        mock_result.text = '{"thought": "Trying", "tool_call": {"name": "file", "arguments": {"action": "read", "path": "missing.py"}}}'

        with patch("tools.agent_ops.actions.subagent.llm.complete", return_value=mock_result):
            with patch("tools.agent_ops.actions.subagent._execute_tool", return_value="Error: file not found"):
                result = agent(
                    action="subagent",
                    role="executor",
                    task="Read missing file",
                    tools="file",
                    max_turns=10,
                )

        assert result["status"] == "error"
        assert result["error_code"] == "TOOL_FAILURES"
        assert result["turns"] == 3

    def test_multi_turn_python_run_blocked(self):
        """python(mode='run') is blocked even if 'python' is in the allowlist."""
        from tools.agent_ops.actions.subagent import _execute_tool
        result = _execute_tool("python", {"mode": "run", "code": "import os; os.system('rm -rf /')"})
        assert "not allowed for subagents" in result
        assert "eval" in result
