"""Tests for the compose type handler — chain multiple workflows sequentially.

The compose handler:
  - Validates that `steps` is a non-empty list of dicts.
  - Runs each step via _execute_workflow().
  - Passes prev_result + step_results from prior steps to subsequent steps.
  - Stops the chain on the first step failure.
  - Returns the full step_results list in the `steps` field.
"""
from __future__ import annotations

from unittest.mock import patch

from tools.workflow_ops.types.compose import _type_compose


class TestComposeValidation:
    """Compose fail-fast parameter guards."""

    def test_compose_requires_steps(self, mock_tracer):
        """Empty steps list -> error."""
        result = _type_compose(goal="test", trace_id="t1", steps=[])
        assert result["status"] == "error"
        assert "steps is required" in result["error"]
        assert result.get("workflow_type") == "compose"
        assert result["trace_id"] == "t1"

    def test_compose_requires_steps_none(self, mock_tracer):
        """steps=None -> error."""
        result = _type_compose(goal="test", trace_id="t2", steps=None)
        assert result["status"] == "error"
        assert "steps is required" in result["error"]

    def test_compose_requires_steps_missing(self, mock_tracer):
        """steps not passed at all -> error."""
        result = _type_compose(goal="test", trace_id="t3")
        assert result["status"] == "error"
        assert "steps is required" in result["error"]

    def test_compose_rejects_non_list_steps(self, mock_tracer):
        """steps must be a list."""
        result = _type_compose(goal="test", trace_id="t4", steps={"type": "research"})
        assert result["status"] == "error"
        assert "non-empty list" in result["error"]

    def test_compose_rejects_non_dict_step(self, mock_tracer):
        """Each step must be a dict."""
        with patch("tools.workflow_ops.helpers._execute_workflow") as mock_exec:
            result = _type_compose(
                goal="test", trace_id="t5",
                steps=["not a dict"],
            )
        assert result["status"] == "error"
        assert "must be a dict" in result["error"]
        mock_exec.assert_not_called()

    def test_compose_rejects_step_missing_type(self, mock_tracer):
        """Each step must have a 'type' field."""
        result = _type_compose(
            goal="test", trace_id="t6",
            steps=[{"goal": "no type"}],
        )
        assert result["status"] == "error"
        assert "missing 'type'" in result["error"]

    def test_compose_rejects_step_missing_goal(self, mock_tracer):
        """Each step must have a 'goal' field."""
        result = _type_compose(
            goal="test", trace_id="t7",
            steps=[{"type": "research"}],
        )
        assert result["status"] == "error"
        assert "missing 'goal'" in result["error"]


class TestComposeExecution:
    """Compose execution paths with valid params."""

    def test_compose_runs_sequentially(self, mock_tracer):
        """Two successful steps — both _execute_workflow calls happen in order."""
        with patch("tools.workflow_ops.helpers._execute_workflow") as mock_exec:
            mock_exec.side_effect = [
                {"status": "success", "result": "step1 done"},
                {"status": "success", "result": "step2 done"},
            ]
            result = _type_compose(
                goal="chain test", trace_id="t-seq",
                steps=[
                    {"type": "research", "goal": "step1"},
                    {"type": "data", "goal": "step2", "code": "print(1)"},
                ],
            )
        assert result["status"] == "success"
        assert mock_exec.call_count == 2
        # First call: research / step1
        first_args = mock_exec.call_args_list[0][0]
        assert first_args[0] == "research"
        assert first_args[1] == "step1"
        assert first_args[2] == "t-seq"
        # Second call: data / step2
        second_args = mock_exec.call_args_list[1][0]
        assert second_args[0] == "data"
        assert second_args[1] == "step2"

    def test_compose_stops_on_failure(self, mock_tracer):
        """Step 1 fails -> step 2 is NOT called."""
        with patch("tools.workflow_ops.helpers._execute_workflow") as mock_exec:
            mock_exec.return_value = {"status": "failed", "error": "step1 crashed"}
            result = _type_compose(
                goal="chain test", trace_id="t-fail",
                steps=[
                    {"type": "research", "goal": "step1"},
                    {"type": "data", "goal": "step2"},
                ],
            )
        assert result["status"] == "failed"
        assert mock_exec.call_count == 1  # only step1 called
        assert result["failed_step"] == 1
        assert result["failed_step_type"] == "research"
        assert "step1 crashed" in result["error"]
        # The single step's result is preserved
        assert len(result["steps"]) == 1
        assert result["steps"][0]["status"] == "failed"

    def test_compose_passes_prev_result(self, mock_tracer):
        """Step 2 receives prev_result (full result dict from step 1) + step_results list."""
        with patch("tools.workflow_ops.helpers._execute_workflow") as mock_exec:
            step1_result = {"status": "success", "result": "step1 done", "data": [1, 2, 3]}
            step2_result = {"status": "success", "result": "step2 done"}
            mock_exec.side_effect = [step1_result, step2_result]
            result = _type_compose(
                goal="chain test", trace_id="t-prev",
                steps=[
                    {"type": "research", "goal": "step1"},
                    {"type": "data", "goal": "step2", "code": "print(1)"},
                ],
            )
        assert result["status"] == "success"
        # First call: no prev_result (no prior steps)
        first_kwargs = mock_exec.call_args_list[0][1]
        assert "prev_result" not in first_kwargs
        # Second call: prev_result == step1 result, step_results has 1 entry
        second_kwargs = mock_exec.call_args_list[1][1]
        assert second_kwargs["prev_result"] == step1_result
        assert len(second_kwargs["step_results"]) == 1
        assert second_kwargs["step_results"][0] == step1_result
        # Type-specific kwargs (code) still flow through
        assert second_kwargs["code"] == "print(1)"

    def test_compose_success_returns_all_steps(self, mock_tracer):
        """Two successful steps -> result.steps has 2 entries + final_result."""
        with patch("tools.workflow_ops.helpers._execute_workflow") as mock_exec:
            step1_result = {"status": "success", "result": "step1 done"}
            step2_result = {"status": "success", "result": "step2 done"}
            mock_exec.side_effect = [step1_result, step2_result]
            result = _type_compose(
                goal="chain test", trace_id="t-all",
                steps=[
                    {"type": "research", "goal": "step1"},
                    {"type": "data", "goal": "step2"},
                ],
            )
        assert result["status"] == "success"
        assert len(result["steps"]) == 2
        assert result["steps"][0] == step1_result
        assert result["steps"][1] == step2_result
        # final_result is the last step's result
        assert result["final_result"] == step2_result
        assert "2 steps" in result["result"]

    def test_compose_three_steps_pass_step_results_history(self, mock_tracer):
        """Three steps: step 3 should receive step_results with 2 prior results."""
        with patch("tools.workflow_ops.helpers._execute_workflow") as mock_exec:
            mock_exec.side_effect = [
                {"status": "success", "result": "s1"},
                {"status": "success", "result": "s2"},
                {"status": "success", "result": "s3"},
            ]
            result = _type_compose(
                goal="chain test", trace_id="t-three",
                steps=[
                    {"type": "research", "goal": "s1"},
                    {"type": "research", "goal": "s2"},
                    {"type": "research", "goal": "s3"},
                ],
            )
        assert result["status"] == "success"
        assert mock_exec.call_count == 3
        # Step 3's step_results should have 2 entries
        third_kwargs = mock_exec.call_args_list[2][1]
        assert len(third_kwargs["step_results"]) == 2
        assert third_kwargs["prev_result"]["result"] == "s2"
