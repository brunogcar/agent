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