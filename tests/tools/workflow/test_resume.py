"""Tests for the resume action — list incomplete + resume specific trace_id.

The resume action has two modes:
  1. workflow(action="resume", trace_id="...") — resume a specific workflow
     by reading its checkpoint.
  2. workflow(action="resume") — list all incomplete workflows via
     scan_incomplete() + get_latest().
"""
from __future__ import annotations

from unittest.mock import patch, MagicMock

from tools.workflow import workflow
from tools.workflow_ops.actions.resume import _action_resume


class TestResumeListIncomplete:
    """Mode 2: workflow(action="resume") with no trace_id lists incomplete
    workflows from the checkpoint journal."""

    def test_resume_lists_incomplete(self, mock_tracer):
        """With no trace_id, resume returns the list of incomplete workflows."""
        with patch("core.observability.checkpoint.scan_incomplete",
                   return_value=["t-1", "t-2"]) as mock_scan, \
             patch("core.observability.checkpoint.get_latest") as mock_get:
            mock_get.side_effect = [
                {
                    "workflow": "autocode",
                    "goal": "fix bug 1",
                    "_checkpoint_node": "node_apply_patch",
                    "status": "running",
                },
                {
                    "workflow": "understand",
                    "goal": "map repo",
                    "_checkpoint_node": "parse_and_store",
                    "status": "running",
                },
            ]
            result = workflow(action="resume", trace_id="")

        assert result["status"] == "success"
        assert result["count"] == 2
        assert len(result["incomplete"]) == 2
        assert result["incomplete"][0]["trace_id"] == "t-1"
        assert result["incomplete"][0]["workflow"] == "autocode"
        assert result["incomplete"][0]["goal"] == "fix bug 1"
        assert result["incomplete"][0]["last_node"] == "node_apply_patch"
        assert result["incomplete"][0]["status"] == "running"
        assert result["incomplete"][1]["trace_id"] == "t-2"
        assert result["incomplete"][1]["workflow"] == "understand"
        mock_scan.assert_called_once()

    def test_resume_no_incomplete(self, mock_tracer):
        """When scan_incomplete returns [], resume returns an empty list
        with a friendly message."""
        with patch("core.observability.checkpoint.scan_incomplete",
                   return_value=[]) as mock_scan, \
             patch("core.observability.checkpoint.get_latest") as mock_get:
            result = workflow(action="resume", trace_id="")

        assert result["status"] == "success"
        assert result["incomplete"] == []
        assert result["count"] == 0
        assert "No incomplete workflows found" in result["message"]
        mock_scan.assert_called_once()
        # get_latest should NOT be called when there are no incomplete IDs
        mock_get.assert_not_called()

    def test_resume_whitespace_trace_id_treated_as_empty(self, mock_tracer):
        """Whitespace-only trace_id should be treated as missing → list mode."""
        with patch("core.observability.checkpoint.scan_incomplete",
                   return_value=[]) as mock_scan:
            result = workflow(action="resume", trace_id="   ")

        assert result["status"] == "success"
        assert result["count"] == 0
        mock_scan.assert_called_once()


class TestResumeSpecificTraceId:
    """Mode 1: workflow(action="resume", trace_id="...") resumes a specific
    workflow by reading its checkpoint + forwarding to the type handler."""

    def test_resume_specific_trace_id(self, mock_tracer, mock_run_workflow):
        """With a trace_id, resume reads the checkpoint + forwards to the
        type handler with resume=True."""
        checkpoint = {
            "workflow": "research",
            "goal": "survey LLM agents",
            "status": "running",  # control field — should NOT be forwarded
            "error": "",          # control field
            "result": "",         # control field
            "messages": [],       # control field
            "trace_id": "t-resume",  # control field
            "_checkpoint_node": "planner",
            "_checkpoint_version": 1,
        }
        with patch("core.observability.checkpoint.get_latest",
                   return_value=checkpoint) as mock_get:
            result = workflow(action="resume", trace_id="t-resume")

        assert result["status"] == "success"
        mock_get.assert_called_once_with("t-resume")
        # The type handler should have called run_workflow with resume=True
        _, kwargs = mock_run_workflow.call_args
        assert kwargs["workflow_type"] == "research"
        assert kwargs["goal"] == "survey LLM agents"
        assert kwargs["trace_id"] == "t-resume"
        assert kwargs["resume"] is True

    def test_resume_forwards_overrides(self, mock_tracer, mock_run_workflow):
        """Non-control fields from the checkpoint (target_file, project_root,
        mode, etc.) are forwarded to the type handler as overrides."""
        checkpoint = {
            "workflow": "autocode",
            "goal": "fix bug",
            "status": "running",
            "target_file": "auth.py",
            "mode": "fix_error",
            "error_msg": "KeyError: user",
            "_checkpoint_node": "node_apply_patch",
        }
        with patch("core.observability.checkpoint.get_latest",
                   return_value=checkpoint):
            result = workflow(action="resume", trace_id="t-over")

        assert result["status"] == "success"
        _, kwargs = mock_run_workflow.call_args
        assert kwargs["workflow_type"] == "autocode"
        assert kwargs["target_file"] == "auth.py"
        assert kwargs["mode"] == "fix_error"
        assert kwargs["error_msg"] == "KeyError: user"
        assert kwargs["resume"] is True


class TestResumeErrors:
    """Error paths for the resume action."""

    def test_resume_no_checkpoint(self, mock_tracer):
        """If trace_id is given but no checkpoint exists, return error."""
        with patch("core.observability.checkpoint.get_latest",
                   return_value=None):
            result = workflow(action="resume", trace_id="t-none")

        assert result["status"] == "error"
        assert "No checkpoint found" in result["error"]
        assert "t-none" in result["error"]
        assert result["trace_id"] == "t-none"

    def test_resume_unknown_workflow_type(self, mock_tracer):
        """If the checkpoint's workflow type isn't in TYPE_DISPATCH,
        return an error."""
        checkpoint = {
            "workflow": "nonexistent_type",
            "goal": "test",
            "status": "running",
        }
        with patch("core.observability.checkpoint.get_latest",
                   return_value=checkpoint):
            result = workflow(action="resume", trace_id="t-unknown")

        assert result["status"] == "error"
        assert "nonexistent_type" in result["error"]
        assert "valid_types" in result

    def test_resume_checkpoint_missing_workflow_field(self, mock_tracer):
        """If the checkpoint has no 'workflow' field, return an error."""
        checkpoint = {
            "goal": "test",
            "status": "running",
            # No 'workflow' key
        }
        with patch("core.observability.checkpoint.get_latest",
                   return_value=checkpoint):
            result = workflow(action="resume", trace_id="t-nowf")

        assert result["status"] == "error"
        assert "workflow" in result["error"].lower()
