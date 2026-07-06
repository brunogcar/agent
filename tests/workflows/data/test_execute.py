"""tests/workflows/data/test_execute.py
Tests for node_execute — code generation + execution, failure routing,
and the code_generated flag.

NOTE: agent and python are imported INSIDE node_execute, so we patch at the
SOURCE modules (tools.agent.agent, tools.python.python), not at
workflows.data_impl.nodes.execute.<name>.
"""
from __future__ import annotations

from unittest.mock import patch

from workflows.data_impl.nodes.execute import node_execute
from workflows.data_impl.routes import route_after_execute


class TestNodeExecuteProvidedCode:
    def test_runs_provided_code_directly(self, base_state):
        """User-provided code skips generation and runs directly."""
        base_state["code"] = "print(sum([1,2,3]))"
        with patch("tools.agent.agent") as mock_agent, \
             patch("tools.python.python") as mock_python:
            mock_python.return_value = {"status": "success", "output": "6"}
            out = node_execute(base_state)

        assert mock_agent.called is False, "agent() must not run when code is provided"
        assert mock_python.called is True
        assert out["output"] == "6"
        assert out["exec_error"] == ""
        # [Fix #5] User-provided code is NOT flagged as generated.
        assert out["code_generated"] is False

    def test_returns_partial_dict(self, base_state):
        """[Fix #1] Return only changed keys, not {**state, ...}."""
        base_state["code"] = "print(1)"
        with patch("tools.python.python") as mock_python:
            mock_python.return_value = {"status": "success", "output": "1"}
            out = node_execute(base_state)
        assert "goal" not in out, "Partial dict must not echo unchanged state keys"
        assert "trace_id" not in out


class TestNodeExecuteCodeGeneration:
    def test_generates_code_when_absent(self, base_state):
        """[Regression] No code -> agent(action='dispatch', role='code')."""
        with patch("tools.agent.agent") as mock_agent, \
             patch("tools.python.python") as mock_python:
            mock_agent.return_value = {
                "status": "success",
                "text": "```python\nprint(sum([1,2,3]))\n```",
                "parsed": {"patch": "print(sum([1,2,3]))"},
                "elapsed": 0.1,
            }
            mock_python.return_value = {"status": "success", "output": "6"}
            out = node_execute(base_state)

        assert mock_agent.called, "agent() must be called from the code-gen path"
        _, kwargs = mock_agent.call_args
        assert kwargs.get("action") == "dispatch", (
            "agent() must be called with action='dispatch' (regresses the v1.5 fix)"
        )
        assert kwargs.get("role") == "code"
        # [Fix #5] LLM-generated code is flagged as generated.
        assert out["code_generated"] is True
        assert out["output"] == "6"
        assert out["exec_error"] == ""

    def test_code_extraction_uses_patch_when_available(self, base_state):
        with patch("tools.agent.agent") as mock_agent, \
             patch("tools.python.python") as mock_python:
            mock_agent.return_value = {
                "status": "success",
                "text": "ignore this text",
                "parsed": {"patch": "print(42)"},
            }
            mock_python.return_value = {"status": "success", "output": "42"}
            node_execute(base_state)
            _, python_kwargs = mock_python.call_args
            assert python_kwargs["code"] == "print(42)", (
                "Structured patch field must be preferred over text/fence"
            )

    def test_code_extraction_falls_back_to_fence(self, base_state):
        """[Fix #9] No patch -> extract from ```python fence."""
        with patch("tools.agent.agent") as mock_agent, \
             patch("tools.python.python") as mock_python:
            mock_agent.return_value = {
                "status": "success",
                "text": "Here:\n```python\nprint(7)\n```",
                "parsed": {},
            }
            mock_python.return_value = {"status": "success", "output": "7"}
            node_execute(base_state)
            _, python_kwargs = mock_python.call_args
            assert "print(7)" in python_kwargs["code"]


class TestNodeExecuteFailureRouting:
    def test_code_gen_failure_sets_exec_error(self, base_state):
        """[Fix #2] Code-gen failure must set exec_error so the router sends it to END."""
        with patch("tools.agent.agent") as mock_agent, \
             patch("tools.python.python") as mock_python:
            mock_agent.return_value = {"status": "error", "error": "model timeout"}
            out = node_execute(base_state)

        assert "exec_error" in out
        assert out["exec_error"], "exec_error must be set on code-gen failure"
        assert out["output"] == ""
        # The router must now send this to END, not critique.
        assert route_after_execute(out) == "failed", (
            "Code-gen failure must route to END (was leaking through to critique)"
        )
        assert mock_python.called is False, "python() must not run when code gen failed"

    def test_execution_failure_sets_exec_error(self, base_state):
        """[Fix #3] Execution failure must set exec_error (and was not logged before)."""
        base_state["code"] = "print(1)"
        with patch("tools.python.python") as mock_python:
            mock_python.return_value = {"status": "error", "error": "SyntaxError: bad"}
            out = node_execute(base_state)

        assert out["exec_error"] == "SyntaxError: bad"
        assert out["output"] == ""
        assert route_after_execute(out) == "failed"

    def test_execution_exception_is_caught(self, base_state):
        """[Fix #8] An unexpected python() exception must become exec_error, not a crash."""
        base_state["code"] = "print(1)"
        with patch("tools.python.python") as mock_python:
            mock_python.side_effect = RuntimeError("sandbox exploded")
            out = node_execute(base_state)
        assert "exec_error" in out
        assert "sandbox exploded" in out["exec_error"]
        assert route_after_execute(out) == "failed"

    def test_code_gen_exception_is_caught(self, base_state):
        """[Fix #8] An unexpected agent() exception must become exec_error, not a crash."""
        with patch("tools.agent.agent") as mock_agent:
            mock_agent.side_effect = RuntimeError("agent boom")
            out = node_execute(base_state)
        assert out["exec_error"]
        assert route_after_execute(out) == "failed"
