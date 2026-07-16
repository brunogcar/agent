"""Tests for LLMClient.complete_with_tools() — native tool-calling loop.

Mocks the internal call() method to simulate LLM responses with/without
tool_calls. Verifies the loop: text-only (0 iterations), tool-call-then-text,
max_iterations cap, tool errors stay in-loop, consecutive errors bail, and
usage aggregation.
"""
from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

from core.llm_backend.response import LLMResponse, ToolCall
from core.llm_backend.tools import ToolDefinition, tool_def_from_meta_tool
from core.llm_backend.client import LLMClient


# ── Fixtures ─────────────────────────────────────────────────────────────────

def _make_tool_def(name="file", actions=None):
    """Build a ToolDefinition for testing."""
    actions = actions or ["read_file", "list_directory"]
    fn = MagicMock()
    fn.__tool_metadata__ = {
        "actions": actions,
        "dispatch": {a: {"help": f"{a} help", "examples": []} for a in actions},
    }
    return tool_def_from_meta_tool(name, fn)


def _text_response(role="executor", model="test-model", text="Done."):
    """Build a text-only LLMResponse (no tool_calls)."""
    return LLMResponse(
        text=text, role=role, model=model,
        usage={"prompt": 10, "completion": 5, "total": 15},
        elapsed=0.1, ok=True, tool_calls=[],
    )


def _tool_call_response(role="executor", model="test-model", tool_calls=None):
    """Build an LLMResponse with tool_calls (no text)."""
    tool_calls = tool_calls or [ToolCall(id="tc_0", name="file", arguments={"action": "read_file", "path": "x.py"})]
    return LLMResponse(
        text="", role=role, model=model,
        usage={"prompt": 20, "completion": 10, "total": 30},
        elapsed=0.2, ok=True, tool_calls=tool_calls,
    )


@pytest.fixture
def mock_client():
    """Build an LLMClient with a mocked provider registry (no real HTTP)."""
    with patch.object(LLMClient, "__init__", lambda self, **kw: None):
        client = LLMClient()
        client._breakers = {}
        # Mock _get_breaker to return a always-OK breaker
        breaker = MagicMock()
        breaker.can_execute.return_value = True
        breaker.record_success = MagicMock()
        breaker.record_failure = MagicMock()
        client._get_breaker = MagicMock(return_value=breaker)
        return client


# ── Tests ────────────────────────────────────────────────────────────────────

class TestCompleteWithToolsImmediateText:
    """LLM returns text immediately (no tool calls) — 0 tool iterations."""

    def test_immediate_text_returns_right_away(self, mock_client):
        """When the LLM returns text with no tool_calls, return it immediately."""
        with patch.object(mock_client, "call", return_value=_text_response(text="Final answer")):
            result = mock_client.complete_with_tools(
                role="executor", system="sys", user="task",
                tools=[_make_tool_def()],
                execute=lambda tc: {"result": "ok"},
            )
        assert result.ok
        assert result.text == "Final answer"
        assert result.tool_calls == []

    def test_immediate_text_aggregates_usage(self, mock_client):
        """Usage from the single LLM call is in the response."""
        with patch.object(mock_client, "call", return_value=_text_response()):
            result = mock_client.complete_with_tools(
                role="executor", system="sys", user="task",
                tools=[_make_tool_def()],
                execute=lambda tc: {},
            )
        assert result.usage["total"] == 15


class TestCompleteWithToolsOneCallThenText:
    """LLM returns 1 tool call, then text — 1 tool iteration."""

    def test_one_tool_call_then_text(self, mock_client):
        """LLM calls a tool, sees the result, then gives final answer."""
        responses = [
            _tool_call_response(tool_calls=[ToolCall(id="tc_0", name="file", arguments={"action": "read_file", "path": "x.py"})]),
            _text_response(text="The file contains..."),
        ]
        call_iter = iter(responses)
        execute_called = []

        def mock_execute(tc):
            execute_called.append(tc)
            return {"content": "file contents here"}

        with patch.object(mock_client, "call", side_effect=lambda **kw: next(call_iter)):
            result = mock_client.complete_with_tools(
                role="executor", system="sys", user="Read x.py",
                tools=[_make_tool_def()],
                execute=mock_execute,
            )
        assert result.ok
        assert result.text == "The file contains..."
        assert len(execute_called) == 1
        assert execute_called[0].name == "file"

    def test_usage_aggregated_across_iterations(self, mock_client):
        """Usage from both the tool-call response + the final text response is summed."""
        responses = [_tool_call_response(), _text_response()]
        call_iter = iter(responses)
        with patch.object(mock_client, "call", side_effect=lambda **kw: next(call_iter)):
            result = mock_client.complete_with_tools(
                role="executor", system="sys", user="task",
                tools=[_make_tool_def()],
                execute=lambda tc: {"result": "ok"},
            )
        # tool_call_response usage: 30, text_response usage: 15 → total 45
        assert result.usage["total"] == 45


class TestCompleteWithToolsMultipleCalls:
    """LLM returns multiple tool calls in one response."""

    def test_two_tool_calls_in_one_response(self, mock_client):
        """Both tool calls are executed before the next LLM call."""
        responses = [
            _tool_call_response(tool_calls=[
                ToolCall(id="tc_0", name="file", arguments={"action": "read_file", "path": "a.py"}),
                ToolCall(id="tc_1", name="file", arguments={"action": "read_file", "path": "b.py"}),
            ]),
            _text_response(text="Both files read."),
        ]
        call_iter = iter(responses)
        executed = []

        with patch.object(mock_client, "call", side_effect=lambda **kw: next(call_iter)):
            result = mock_client.complete_with_tools(
                role="executor", system="sys", user="Read both",
                tools=[_make_tool_def()],
                execute=lambda tc: executed.append(tc.name) or {"content": "ok"},
            )
        assert result.ok
        assert len(executed) == 2


class TestCompleteWithToolsMaxIterations:
    """max_iterations cap prevents runaway loops."""

    def test_max_iterations_exceeded(self, mock_client):
        """LLM keeps returning tool_calls — bail after max_iterations."""
        # Always return a tool call (never text)
        with patch.object(mock_client, "call", return_value=_tool_call_response()):
            result = mock_client.complete_with_tools(
                role="executor", system="sys", user="task",
                tools=[_make_tool_def()],
                execute=lambda tc: {"result": "ok"},
                max_iterations=3,
            )
        assert not result.ok
        assert "max_iterations" in result.error
        assert "3" in result.error


class TestCompleteWithToolsErrors:
    """Tool errors stay in-loop; consecutive errors bail."""

    def test_tool_error_stays_in_loop(self, mock_client):
        """A single tool error doesn't break the loop — the LLM sees the error + adapts."""
        responses = [
            _tool_call_response(),
            _text_response(text="Recovered from error."),
        ]
        call_iter = iter(responses)

        def failing_execute(tc):
            raise ValueError("file not found")

        with patch.object(mock_client, "call", side_effect=lambda **kw: next(call_iter)):
            result = mock_client.complete_with_tools(
                role="executor", system="sys", user="task",
                tools=[_make_tool_def()],
                execute=failing_execute,
            )
        assert result.ok  # The loop continued past the error
        assert result.text == "Recovered from error."

    def test_consecutive_errors_bail(self, mock_client):
        """max_consecutive_errors=3 bails after 3 consecutive tool errors."""
        # Always return tool calls (so the loop keeps going)
        with patch.object(mock_client, "call", return_value=_tool_call_response()):
            result = mock_client.complete_with_tools(
                role="executor", system="sys", user="task",
                tools=[_make_tool_def()],
                execute=lambda tc: (_ for _ in ()).throw(ValueError("broken")),
                max_iterations=10,
                max_consecutive_errors=3,
            )
        assert not result.ok
        assert "consecutive tool errors" in result.error

    def test_error_reset_on_success(self, mock_client):
        """A successful tool call resets the consecutive error counter."""
        call_count = [0]

        def alternating_execute(tc):
            call_count[0] += 1
            if call_count[0] % 2 == 1:
                raise ValueError("odd error")
            return {"result": "ok"}

        # 6 tool-call responses, then text — but with alternating errors,
        # consecutive_errors never reaches 3 (max is 1 before reset)
        responses = [_tool_call_response()] * 6 + [_text_response(text="Done")]
        call_iter = iter(responses)

        with patch.object(mock_client, "call", side_effect=lambda **kw: next(call_iter)):
            result = mock_client.complete_with_tools(
                role="executor", system="sys", user="task",
                tools=[_make_tool_def()],
                execute=alternating_execute,
                max_iterations=10,
                max_consecutive_errors=3,
            )
        assert result.ok
        assert result.text == "Done"


class TestCompleteWithToolsLLMError:
    """LLM errors (not tool errors) bail immediately."""

    def test_llm_error_bails_immediately(self, mock_client):
        """If call() returns ok=False, the loop exits immediately."""
        error_resp = LLMResponse.from_error("executor", "test-model", "LM Studio unreachable", 0.1)
        with patch.object(mock_client, "call", return_value=error_resp):
            result = mock_client.complete_with_tools(
                role="executor", system="sys", user="task",
                tools=[_make_tool_def()],
                execute=lambda tc: {},
            )
        assert not result.ok
        assert "LM Studio unreachable" in result.error


class TestCompleteWithToolsContextAndContent:
    """context + content params build messages correctly."""

    def test_context_and_content_in_messages(self, mock_client):
        """context + content are appended to the user message (like complete())."""
        captured_messages = []

        def capture_call(**kw):
            captured_messages.append(kw.get("messages", []))
            return _text_response()

        with patch.object(mock_client, "call", side_effect=capture_call):
            mock_client.complete_with_tools(
                role="executor", system="sys", user="task",
                tools=[_make_tool_def()],
                execute=lambda tc: {},
                context="background info",
                content="extra content",
            )
        msgs = captured_messages[0]
        # system + user(context) + assistant(Understood) + user(task+content)
        assert len(msgs) == 4
        assert msgs[0]["role"] == "system"
        assert "background info" in msgs[1]["content"]
        assert msgs[2]["content"] == "Understood."
        assert "task" in msgs[3]["content"]
        assert "extra content" in msgs[3]["content"]
