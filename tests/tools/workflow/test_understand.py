"""Tests for the understand type handler validation.

Understand builds a Codebase Knowledge Graph for a specific project
directory. It requires project_root to know where to scan and where to
store artifacts.

[Bug #3 regression test] project_root must be forwarded to run_workflow —
previously validated but never forwarded, causing understand to default to
agent root instead of the specified project directory.
"""
from __future__ import annotations

from tools.workflow import workflow


class TestUnderstandValidation:
    """Understand fail-fast parameter guards."""

    def test_missing_project_root(self, mock_tracer):
        """project_root is required for understand workflow."""
        result = workflow(
            action="run", type="understand",
            goal="build knowledge graph", trace_id="t1",
        )
        assert result["status"] == "error"
        assert "project_root is required" in result["error"]
        assert result["trace_id"] == "t1"
        assert result.get("workflow_type") == "understand"

    def test_whitespace_project_root(self, mock_tracer):
        """Whitespace-only project_root should be treated as missing."""
        result = workflow(
            action="run", type="understand",
            goal="build kg", project_root="   ", trace_id="t2",
        )
        assert result["status"] == "error"
        assert "project_root is required" in result["error"]

    def test_missing_goal(self, mock_tracer):
        """goal is required even for understand."""
        result = workflow(
            action="run", type="understand",
            goal="", project_root="/path/to/repo", trace_id="t3",
        )
        assert result["status"] == "error"
        assert "goal is required" in result["error"].lower()


class TestUnderstandExecution:
    """Understand execution paths with valid params."""

    def test_successful_execution(self, mock_tracer, mock_run_workflow):
        """Valid params should execute the understand workflow."""
        result = workflow(
            action="run", type="understand",
            goal="Build knowledge graph",
            project_root="/path/to/project", trace_id="t4",
        )
        assert result["status"] == "success"
        assert result["trace_id"] == "t4"
        mock_run_workflow.assert_called_once()

    def test_project_root_forwarded_to_run_workflow(self, mock_tracer, mock_run_workflow):
        """[Bug #3] project_root must be forwarded to run_workflow.

        Previously validated but never forwarded — understand defaulted to
        agent root instead of the specified project directory.
        """
        workflow(
            action="run", type="understand",
            goal="Build knowledge graph",
            project_root="/path/to/project", trace_id="t5",
        )
        _, kwargs = mock_run_workflow.call_args
        assert kwargs.get("project_root") == "/path/to/project", (
            "project_root must be forwarded to run_workflow for understand workflow."
        )

    def test_workflow_type_is_understand(self, mock_tracer, mock_run_workflow):
        """run_workflow must receive workflow_type='understand'."""
        workflow(
            action="run", type="understand",
            goal="kg", project_root="/repo", trace_id="t6",
        )
        _, kwargs = mock_run_workflow.call_args
        assert kwargs["workflow_type"] == "understand"
