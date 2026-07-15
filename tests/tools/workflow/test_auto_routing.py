"""Tests for the auto type handler — router dispatch + confidence guard.

The auto type calls core.router.router.route(goal, trace_id=trace_id) to
classify the goal and dynamically select the correct workflow.

Three outcomes:
  1. Router returns workflow="direct" — return routing info to the LLM.
  2. Router returns confidence="low" — return clarifying questions.
     [Bug #6] This guard fires EVEN IF clarifying_questions is empty.
  3. Router returns a specific workflow type — delegate to TYPE_DISPATCH.
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

from tools.workflow import workflow
from tests.tools.workflow.conftest import make_mock_decision


class TestAutoRouting:
    """Auto-routing dispatch logic."""

    def test_auto_routes_to_direct(self, mock_tracer, mock_router):
        """If Router says 'direct', tool should return routing info, not execute."""
        mock_router.return_value = make_mock_decision(
            workflow="direct", tool="web", reason="simple search",
        )

        with patch("workflows.base.run_workflow") as mock_run:
            result = workflow(
                action="run", type="auto",
                goal="search the web", trace_id="t-direct",
            )

        assert result["status"] == "routed"
        assert result["workflow"] == "direct"
        assert result["tool"] == "web"
        assert result["reason"] == "simple search"
        assert result["trace_id"] == "t-direct"
        # Should NOT have executed the workflow
        mock_run.assert_not_called()

    def test_auto_routes_to_workflow(self, mock_tracer, mock_router, mock_run_workflow):
        """If Router picks a workflow with high confidence, it should execute it."""
        mock_router.return_value = make_mock_decision(
            workflow="research", confidence="high",
        )

        result = workflow(
            action="run", type="auto",
            goal="research ai", trace_id="t-route",
        )

        assert result["status"] == "success"
        assert result["trace_id"] == "t-route"
        mock_run_workflow.assert_called_once()
        _, kwargs = mock_run_workflow.call_args
        assert kwargs["workflow_type"] == "research"


class TestAutoRoutingLowConfidence:
    """[Bug #6] Low confidence must abort EVEN IF clarifying_questions is empty.

    Previously: `if confidence == 'low' and clarifying_questions:` — if
    questions were empty/None, low confidence fell through to execution.
    """

    def test_low_confidence_no_questions_still_aborts(self, mock_tracer, mock_router):
        """Low confidence with empty clarifying_questions must still abort."""
        mock_router.return_value = make_mock_decision(
            workflow="research", confidence="low",
            clarifying_questions=[],  # Empty — must still abort
        )

        with patch("workflows.base.run_workflow") as mock_run:
            result = workflow(
                action="run", type="auto",
                goal="vague goal", trace_id="t-low-empty",
            )

        assert result["status"] == "needs_clarification", (
            "Low confidence must abort execution even when clarifying_questions is empty."
        )
        assert result["trace_id"] == "t-low-empty"
        # Should NOT have executed the workflow
        mock_run.assert_not_called()
        # Should provide a default question when none were given
        assert len(result["clarifying_questions"]) >= 1

    def test_low_confidence_with_questions_aborts(self, mock_tracer, mock_router):
        """Low confidence with clarifying_questions must abort and forward questions."""
        mock_router.return_value = make_mock_decision(
            workflow="research", confidence="low",
            clarifying_questions=["What scope?", "Which files?"],
        )

        with patch("workflows.base.run_workflow") as mock_run:
            result = workflow(
                action="run", type="auto",
                goal="vague goal", trace_id="t-low-q",
            )

        assert result["status"] == "needs_clarification"
        assert result["clarifying_questions"] == ["What scope?", "Which files?"]
        mock_run.assert_not_called()

    def test_low_confidence_none_questions_still_aborts(self, mock_tracer, mock_router):
        """Low confidence with clarifying_questions=None must still abort."""
        mock_router.return_value = make_mock_decision(
            workflow="research", confidence="low",
            clarifying_questions=None,
        )

        with patch("workflows.base.run_workflow") as mock_run:
            result = workflow(
                action="run", type="auto",
                goal="vague goal", trace_id="t-low-none",
            )

        assert result["status"] == "needs_clarification"
        mock_run.assert_not_called()
        assert len(result["clarifying_questions"]) >= 1


class TestAutoRoutingHighConfidence:
    """High/medium confidence must proceed to workflow execution."""

    def test_high_confidence_proceeds_to_execution(
        self, mock_tracer, mock_router, mock_run_workflow,
    ):
        """High confidence should execute the routed workflow."""
        mock_router.return_value = make_mock_decision(
            workflow="research", confidence="high",
            clarifying_questions=[],
        )

        result = workflow(
            action="run", type="auto",
            goal="clear goal", trace_id="t-high",
        )
        assert result["status"] == "success"
        mock_run_workflow.assert_called_once()

    def test_medium_confidence_proceeds_to_execution(
        self, mock_tracer, mock_router, mock_run_workflow,
    ):
        """Medium confidence should also execute the routed workflow."""
        mock_router.return_value = make_mock_decision(
            workflow="data", confidence="medium",
        )

        result = workflow(
            action="run", type="auto",
            goal="analyze data", trace_id="t-med",
        )
        assert result["status"] == "success"
        _, kwargs = mock_run_workflow.call_args
        assert kwargs["workflow_type"] == "data"


class TestAutoRoutingFailures:
    """Router failures should return clean error dicts."""

    def test_router_exception_returns_clean_error(self, mock_tracer, mock_router):
        """If router.route() raises, the tool should return a clean error."""
        mock_router.side_effect = RuntimeError("router model unavailable")

        result = workflow(
            action="run", type="auto",
            goal="anything", trace_id="t-router-err",
        )
        assert result["status"] == "error"
        assert "Failed to route workflow" in result["error"]
        assert "router model unavailable" in result["error"]
        assert result["trace_id"] == "t-router-err"

    def test_auto_missing_goal_returns_error(self, mock_tracer, mock_router):
        """goal is required even before the router is called."""
        result = workflow(
            action="run", type="auto",
            goal="", trace_id="t-no-goal",
        )
        assert result["status"] == "error"
        assert "goal is required" in result["error"].lower()
        # Router should NOT have been called
        mock_router.assert_not_called()
