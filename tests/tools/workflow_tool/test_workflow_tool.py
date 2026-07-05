"""
tests/tools/workflow_tool/test_workflow_tool.py
Tests for the Workflow meta-tool, focusing on P0-3 hardening 
(strict type validation, fail-fast parameter guards, and guaranteed trace_id observability).
"""
import pytest
from unittest.mock import patch, MagicMock

from tools.workflow_tool import workflow, _make_error, VALID_WORKFLOWS

# =============================================================================
# 1. Helper & Basic Validation Tests
# =============================================================================
class TestMakeError:
    def test_includes_trace_id(self):
        err = _make_error("something broke", "trace-123")
        assert err["status"] == "error"
        assert err["error"] == "something broke"
        assert err["trace_id"] == "trace-123"

    def test_includes_extra_kwargs(self):
        err = _make_error("bad type", "trace-456", valid_types=["a", "b"])
        assert err["valid_types"] == ["a", "b"]

class TestWorkflowValidation:
    @patch("tools.workflow_tool.tracer")
    def test_generates_trace_id_if_missing(self, mock_tracer):
        mock_tracer.new_trace.return_value = "generated-trace"
        # Invalid type to trigger early return
        res = workflow(type="invalid", goal="test")
        assert res["trace_id"] == "generated-trace"
        mock_tracer.new_trace.assert_called_once()

    @patch("tools.workflow_tool.tracer")
    def test_invalid_workflow_type(self, mock_tracer):
        res = workflow(type="coding", goal="test", trace_id="t1")
        assert res["status"] == "error"
        assert "Invalid workflow type" in res["error"]
        assert res["trace_id"] == "t1"
        assert "valid_types" in res

    @patch("tools.workflow_tool.tracer")
    def test_missing_goal(self, mock_tracer):
        res = workflow(type="research", goal="", trace_id="t2")
        assert res["status"] == "error"
        assert "goal parameter is required" in res["error"]
        assert res["trace_id"] == "t2"

# =============================================================================
# 2. Autocode Fail-Fast Guards
# =============================================================================
class TestAutocodeValidation:
    @patch("tools.workflow_tool.tracer")
    def test_missing_target_file(self, mock_tracer):
        res = workflow(type="autocode", goal="fix it", trace_id="t3")
        assert res["status"] == "error"
        assert "target_file is required" in res["error"]

    @patch("tools.workflow_tool.tracer")
    def test_fix_error_missing_msg(self, mock_tracer):
        res = workflow(type="autocode", goal="fix it", target_file="a.py", mode="fix_error", trace_id="t4")
        assert res["status"] == "error"
        assert "error_msg is required" in res["error"]

    @patch("tools.workflow_tool.tracer")
    def test_add_feature_missing_desc(self, mock_tracer):
        res = workflow(type="autocode", goal="add it", target_file="a.py", mode="add_feature", trace_id="t5")
        assert res["status"] == "error"
        assert "feature_desc is required" in res["error"]

# =============================================================================
# 3. Auto-Routing Logic (Aligned exactly with core/router.py)
# =============================================================================
class TestAutoRouting:
    @patch("core.router.router.route")
    def test_auto_routes_to_direct(self, mock_route):
        """If Router says 'direct', tool should return routing info, not execute."""
        # Mock the RoutingDecision object returned by core.router.router.route()
        mock_decision = MagicMock()
        mock_decision.workflow = "direct"
        mock_decision.tool = "web"
        mock_decision.reason = "simple search"
        mock_route.return_value = mock_decision
        
        with patch("tools.workflow_tool.tracer"):
            res = workflow(type="auto", goal="search web", trace_id="t6")
        
        assert res["status"] == "routed"
        assert res["workflow"] == "direct"
        assert res["tool"] == "web"
        assert res["trace_id"] == "t6"

    @patch("core.router.router.route")
    @patch("workflows.base.run_workflow")
    def test_auto_routes_to_workflow(self, mock_run, mock_route):
        """If Router picks a workflow, it should execute it."""
        mock_decision = MagicMock()
        mock_decision.workflow = "research"
        mock_route.return_value = mock_decision
        
        mock_run.return_value = {"status": "success", "data": "done"}
        
        with patch("tools.workflow_tool.tracer"):
            res = workflow(type="auto", goal="research ai", trace_id="t7")
        
        assert res["status"] == "success"
        assert res["trace_id"] == "t7"
        mock_run.assert_called_once()
        
        # Verify it was called with the routed workflow type
        args, kwargs = mock_run.call_args
        assert kwargs["workflow_type"] == "research"

# =============================================================================
# 4. Execution & Observability
# =============================================================================
class TestWorkflowExecution:
    @patch("tools.workflow_tool.tracer")
    @patch("workflows.base.run_workflow")
    def test_successful_execution_adds_trace_id(self, mock_run, mock_tracer):
        """Ensure trace_id is injected into successful workflow results."""
        mock_run.return_value = {"status": "success", "result": "ok"}
        res = workflow(type="data", goal="analyze", code="print(1)", trace_id="t8")
        
        assert res["status"] == "success"
        assert res["trace_id"] == "t8"

    @patch("tools.workflow_tool.tracer")
    @patch("workflows.base.run_workflow")
    def test_execution_exception_returns_clean_error(self, mock_run, mock_tracer):
        """Ensure LangGraph crashes are caught and returned as clean error dicts."""
        mock_run.side_effect = RuntimeError("LangGraph node crashed")
        res = workflow(type="research", goal="test", trace_id="t9")

        assert res["status"] == "error"
        assert "Workflow execution failed" in res["error"]
        assert res["trace_id"] == "t9"


# =============================================================================
# 5. Regression: Bug #3, #4, #5, #6
# =============================================================================
class TestWorkflowTypeLiteral:
    """Bug #4: WorkflowType Literal must include 'understand'."""

    def test_workflow_type_includes_understand(self):
        """The WorkflowType Literal must include 'understand' for type checkers."""
        from typing import get_args
        from tools.workflow_tool import WorkflowType
        args = get_args(WorkflowType)
        assert "understand" in args, (
            f"WorkflowType Literal must include 'understand'. Got: {args}"
        )

    def test_workflow_type_includes_deep_research(self):
        """The WorkflowType Literal must include 'deep_research'."""
        from typing import get_args
        from tools.workflow_tool import WorkflowType
        args = get_args(WorkflowType)
        assert "deep_research" in args, (
            f"WorkflowType Literal must include 'deep_research'. Got: {args}"
        )

    def test_workflow_type_excludes_report(self):
        """The WorkflowType Literal must NOT include 'report' — it's a tool, not a workflow."""
        from typing import get_args
        from tools.workflow_tool import WorkflowType
        args = get_args(WorkflowType)
        assert "report" not in args, (
            f"WorkflowType Literal must NOT include 'report' (it's a tool). Got: {args}"
        )

    def test_valid_workflows_excludes_report(self):
        """VALID_WORKFLOWS must NOT include 'report'."""
        assert "report" not in VALID_WORKFLOWS, (
            "VALID_WORKFLOWS must not include 'report' — it's a tool, not a workflow."
        )

    def test_valid_workflows_includes_deep_research(self):
        """VALID_WORKFLOWS must include 'deep_research'."""
        assert "deep_research" in VALID_WORKFLOWS, (
            "VALID_WORKFLOWS must include 'deep_research' — it's a real workflow."
        )

    def test_workflow_type_matches_valid_workflows(self):
        """WorkflowType Literal should match VALID_WORKFLOWS (minus 'auto' which is a mode)."""
        from typing import get_args
        from tools.workflow_tool import WorkflowType
        args = set(get_args(WorkflowType))
        # Every Literal value should be in VALID_WORKFLOWS
        assert args.issubset(VALID_WORKFLOWS), (
            f"WorkflowType contains values not in VALID_WORKFLOWS: {args - VALID_WORKFLOWS}"
        )


class TestUnderstandDocstring:
    """Bug #5: workflow() docstring must mention 'understand'."""

    def test_docstring_includes_understand(self):
        """The workflow() docstring must list 'understand' for LLM discovery."""
        from tools.workflow_tool import workflow
        assert "understand" in workflow.__doc__.lower(), (
            "workflow() docstring must mention 'understand' — LLM uses the docstring "
            "to discover available workflows."
        )


class TestUnderstandProjectRoot:
    """Bug #3: understand workflow must forward project_root to run_workflow."""

    @patch("tools.workflow_tool.tracer")
    @patch("workflows.base.run_workflow")
    def test_understand_forwards_project_root(self, mock_run, mock_tracer):
        """project_root must be passed to run_workflow for understand workflow.

        Previously validated but never forwarded — understand defaulted to
        agent root instead of the specified project directory.
        """
        mock_run.return_value = {"status": "success", "result": "indexed"}
        res = workflow(
            type="understand",
            goal="Build knowledge graph",
            project_root="/path/to/project",
            trace_id="t-understand",
        )

        assert res["status"] == "success"
        mock_run.assert_called_once()
        _, kwargs = mock_run.call_args
        assert kwargs.get("project_root") == "/path/to/project", (
            "project_root must be forwarded to run_workflow for understand workflow."
        )

    @patch("tools.workflow_tool.tracer")
    def test_understand_missing_project_root_returns_error(self, mock_tracer):
        """project_root is required for understand workflow."""
        res = workflow(type="understand", goal="test", trace_id="t-no-root")
        assert res["status"] == "error"
        assert "project_root is required" in res["error"]


class TestAutoRoutingLowConfidenceGap:
    """Bug #6: low confidence must abort EVEN IF clarifying_questions is empty.

    Previously: `if confidence == 'low' and clarifying_questions:` — if
    questions were empty/None, low confidence fell through to execution.
    """

    @patch("tools.workflow_tool.tracer")
    @patch("core.router.router.route")
    def test_low_confidence_no_questions_still_aborts(self, mock_route, mock_tracer):
        """Low confidence with empty clarifying_questions must still abort."""
        mock_decision = MagicMock()
        mock_decision.workflow = "research"
        mock_decision.confidence = "low"
        mock_decision.clarifying_questions = []  # Empty — must still abort
        mock_route.return_value = mock_decision

        with patch("workflows.base.run_workflow") as mock_run:
            res = workflow(type="auto", goal="vague goal", trace_id="t-low-conf")

        assert res["status"] == "needs_clarification", (
            "Low confidence must abort execution even when clarifying_questions is empty. "
            "Previously fell through to execution — defeating the guard's purpose."
        )
        assert "trace_id" in res
        # Should NOT have executed the workflow
        mock_run.assert_not_called()
        # Should provide a default question when none were given
        assert len(res["clarifying_questions"]) >= 1

    @patch("tools.workflow_tool.tracer")
    @patch("core.router.router.route")
    def test_low_confidence_with_questions_aborts(self, mock_route, mock_tracer):
        """Low confidence with clarifying_questions must abort and forward questions."""
        mock_decision = MagicMock()
        mock_decision.workflow = "research"
        mock_decision.confidence = "low"
        mock_decision.clarifying_questions = ["What scope?", "Which files?"]
        mock_route.return_value = mock_decision

        with patch("workflows.base.run_workflow") as mock_run:
            res = workflow(type="auto", goal="vague goal", trace_id="t-low-conf-2")

        assert res["status"] == "needs_clarification"
        assert res["clarifying_questions"] == ["What scope?", "Which files?"]
        mock_run.assert_not_called()

    @patch("tools.workflow_tool.tracer")
    @patch("core.router.router.route")
    @patch("workflows.base.run_workflow")
    def test_high_confidence_proceeds_to_execution(self, mock_run, mock_route, mock_tracer):
        """High/medium confidence must proceed to workflow execution."""
        mock_decision = MagicMock()
        mock_decision.workflow = "research"
        mock_decision.confidence = "high"
        mock_decision.clarifying_questions = []
        mock_route.return_value = mock_decision
        mock_run.return_value = {"status": "success", "result": "done"}

        res = workflow(type="auto", goal="clear goal", trace_id="t-high-conf")
        assert res["status"] == "success"
        mock_run.assert_called_once()