"""Tests for the templates action + the `template` param on the run action.

The templates action lists available workflow templates from
tools/workflow_ops/templates/. The `template` param on the `run` action
loads a template's pre-set params, merges with caller params (caller wins),
and forwards to the type handler.
"""
from __future__ import annotations

from unittest.mock import patch, MagicMock

from tools.workflow import workflow
from tools.workflow_ops.templates._registry import (
    get_template,
    list_templates,
    TEMPLATES,
)


class TestTemplatesAction:
    """The templates action lists available workflow templates."""

    def test_list_templates(self, mock_tracer):
        """Calling the templates action should return all 4 templates."""
        result = workflow(action="templates")
        assert result["status"] == "success"
        assert result["count"] == 4
        names = {t["name"] for t in result["templates"]}
        assert names == {"bug-fix", "refactor", "index-codebase", "index-quick"}

    def test_list_templates_has_required_fields(self, mock_tracer):
        """Each template should have name, type, description, params, required."""
        result = workflow(action="templates")
        for t in result["templates"]:
            assert "name" in t
            assert "type" in t
            assert "description" in t
            assert "params" in t
            assert "required" in t
            # The internal _source_file key should NOT be exposed
            assert "_source_file" not in t

    def test_list_templates_includes_trace_id(self, mock_tracer):
        """The templates action should echo the trace_id if provided."""
        result = workflow(action="templates", trace_id="t-tmpl")
        assert result["trace_id"] == "t-tmpl"


class TestGetTemplate:
    """Direct tests on the template loader (templates._registry)."""

    def test_get_template_bug_fix(self):
        """get_template('bug-fix') should return the autocode fix_error template."""
        t = get_template("bug-fix")
        assert t is not None
        assert t["name"] == "bug-fix"
        assert t["type"] == "autocode"
        assert t["params"]["mode"] == "fix_error"
        assert "target_file" in t["required"]
        assert "error_msg" in t["required"]
        assert t["_source_file"] == "bug-fix.json"

    def test_get_template_refactor(self):
        """get_template('refactor') should return the autocode improve template."""
        t = get_template("refactor")
        assert t is not None
        assert t["name"] == "refactor"
        assert t["type"] == "autocode"
        assert t["params"]["mode"] == "improve"
        assert "target_file" in t["required"]

    def test_get_template_index_codebase(self):
        """get_template('index-codebase') should return the understand full template."""
        t = get_template("index-codebase")
        assert t is not None
        assert t["name"] == "index-codebase"
        assert t["type"] == "understand"
        assert t["params"]["skip_embeddings"] is False
        assert "project_root" in t["required"]

    def test_get_template_index_quick(self):
        """get_template('index-quick') should return the understand graph-only template."""
        t = get_template("index-quick")
        assert t is not None
        assert t["name"] == "index-quick"
        assert t["type"] == "understand"
        assert t["params"]["skip_embeddings"] is True
        assert "project_root" in t["required"]

    def test_get_template_not_found(self):
        """get_template('nonexistent') should return None."""
        assert get_template("nonexistent") is None

    def test_get_template_empty_name(self):
        """get_template('') should return None (defensive)."""
        assert get_template("") is None

    def test_list_templates_returns_4(self):
        """list_templates() should return all 4 templates as a list."""
        templates = list_templates()
        assert len(templates) == 4
        names = {t["name"] for t in templates}
        assert names == {"bug-fix", "refactor", "index-codebase", "index-quick"}

    def test_templates_dict_has_4_entries(self):
        """The TEMPLATES dict should have 4 entries keyed by name."""
        assert len(TEMPLATES) == 4
        assert "bug-fix" in TEMPLATES
        assert "refactor" in TEMPLATES
        assert "index-codebase" in TEMPLATES
        assert "index-quick" in TEMPLATES


class TestRunWithTemplate:
    """The `run` action with the `template` param loads + merges params."""

    def test_run_with_template_bug_fix(self, mock_tracer, mock_run_workflow):
        """workflow(action="run", template="bug-fix", target_file=...,
        error_msg=...) should forward to the autocode type handler with
        mode=fix_error + the merged params."""
        result = workflow(
            action="run", template="bug-fix",
            target_file="auth.py",
            error_msg="KeyError: user",
            trace_id="t-bugfix",
        )
        assert result["status"] == "success"
        _, kwargs = mock_run_workflow.call_args
        # Type comes from the template
        assert kwargs["workflow_type"] == "autocode"
        # Template params are forwarded
        assert kwargs["mode"] == "fix_error"
        assert "Fix the bug" in kwargs["goal"]
        # Caller params are forwarded
        assert kwargs["target_file"] == "auth.py"
        assert kwargs["error_msg"] == "KeyError: user"

    def test_run_with_template_refactor(self, mock_tracer, mock_run_workflow):
        """workflow(action="run", template="refactor", target_file=...)
        should forward to the autocode type handler with mode=improve +
        a goal referencing the target_file."""
        result = workflow(
            action="run", template="refactor",
            target_file="utils.py",
            trace_id="t-refactor",
        )
        assert result["status"] == "success"
        _, kwargs = mock_run_workflow.call_args
        assert kwargs["workflow_type"] == "autocode"
        assert kwargs["mode"] == "improve"
        assert "utils.py" in kwargs["goal"]

    def test_run_with_template_index_codebase(self, mock_tracer, mock_run_workflow):
        """workflow(action="run", template="index-codebase",
        project_root=...) should forward to the understand type handler
        with skip_embeddings=False."""
        result = workflow(
            action="run", template="index-codebase",
            project_root="/repo",
            trace_id="t-index",
        )
        assert result["status"] == "success"
        _, kwargs = mock_run_workflow.call_args
        assert kwargs["workflow_type"] == "understand"
        assert kwargs["project_root"] == "/repo"
        assert kwargs.get("skip_embeddings") is False

    def test_run_with_template_index_quick(self, mock_tracer, mock_run_workflow):
        """workflow(action="run", template="index-quick", project_root=...)
        should forward to the understand type handler with skip_embeddings=True."""
        result = workflow(
            action="run", template="index-quick",
            project_root="/repo",
            trace_id="t-quick",
        )
        assert result["status"] == "success"
        _, kwargs = mock_run_workflow.call_args
        assert kwargs["workflow_type"] == "understand"
        assert kwargs["project_root"] == "/repo"
        assert kwargs.get("skip_embeddings") is True

    def test_run_with_template_not_found(self, mock_tracer):
        """workflow(action="run", template="nonexistent", ...) should return
        an error listing available templates."""
        result = workflow(
            action="run", template="nonexistent",
            target_file="x.py", error_msg="err",
            trace_id="t-bad-tmpl",
        )
        assert result["status"] == "error"
        assert "Template not found" in result["error"]
        assert "nonexistent" in result["error"]
        assert "available_templates" in result
        # All 4 templates should be listed as available
        assert "bug-fix" in result["available_templates"]
        assert "refactor" in result["available_templates"]
        assert "index-codebase" in result["available_templates"]
        assert "index-quick" in result["available_templates"]

    def test_run_with_template_override(self, mock_tracer, mock_run_workflow):
        """Caller params should override template params.

        bug-fix template sets goal="Fix the bug described in error_msg".
        If the caller passes a different goal, the caller's goal wins.
        """
        result = workflow(
            action="run", template="bug-fix",
            target_file="auth.py",
            error_msg="KeyError: user",
            goal="Custom caller goal — fix the auth bug ASAP",
            trace_id="t-override",
        )
        assert result["status"] == "success"
        _, kwargs = mock_run_workflow.call_args
        # Caller's goal wins over template's goal
        assert kwargs["goal"] == "Custom caller goal — fix the auth bug ASAP"
        # Template's mode still applies (caller didn't override mode)
        assert kwargs["mode"] == "fix_error"

    def test_run_with_template_missing_required(self, mock_tracer):
        """workflow(action="run", template="bug-fix", target_file=...)
        without error_msg should return an error listing the missing
        required params."""
        result = workflow(
            action="run", template="bug-fix",
            target_file="auth.py",
            # error_msg missing — required by bug-fix template
            trace_id="t-missing-req",
        )
        assert result["status"] == "error"
        assert "missing" in result["error"].lower() or "required" in result["error"].lower()
        assert "error_msg" in result.get("missing", [])
        assert "error_msg" in result.get("required", [])
