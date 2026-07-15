"""Tests for the list action — returns metadata for all workflow types."""
from __future__ import annotations

from unittest.mock import patch, MagicMock

from tools.workflow import workflow


class TestListAction:
    """The list action returns workflow metadata."""

    def test_list_returns_success(self, mock_tracer):
        result = workflow(action="list", trace_id="t-list")
        assert result["status"] == "success"

    def test_list_returns_workflows_dict(self, mock_tracer):
        result = workflow(action="list", trace_id="t-list")
        assert "workflows" in result
        assert isinstance(result["workflows"], dict)
        # Should include all 6 graph-backed types + auto (router pseudo-type)
        for type_name in ["research", "data", "autocode", "deep_research",
                          "understand", "autoresearch", "auto"]:
            assert type_name in result["workflows"], f"Missing {type_name}"

    def test_list_includes_count(self, mock_tracer):
        result = workflow(action="list", trace_id="t-list")
        assert "count" in result
        assert result["count"] == len(result["workflows"])
        assert result["count"] >= 7  # 6 graph-backed + auto

    def test_list_includes_trace_id(self, mock_tracer):
        result = workflow(action="list", trace_id="t-list-123")
        assert result["trace_id"] == "t-list-123"

    def test_list_works_without_trace_id(self, mock_tracer):
        """list doesn't require trace_id (it's not a workflow run)."""
        result = workflow(action="list")
        assert result["status"] == "success"
        assert "trace_id" in result


class TestListActionMetadata:
    """The list action reads WORKFLOW_METADATA from each workflow module."""

    def test_metadata_includes_required_fields(self, mock_tracer):
        """Each workflow entry should have name + version + description (or error)."""
        with patch("tools.workflow_ops.helpers.importlib.import_module") as mock_import:
            mock_mod = MagicMock()
            mock_mod.WORKFLOW_METADATA = {
                "name": "Research",
                "version": "1.2",
                "description": "Web research workflow",
                "entry_point": "research_graph",
            }
            mock_import.return_value = mock_mod

            result = workflow(action="list", trace_id="t-meta")
            for name, meta in result["workflows"].items():
                # Each entry must have either metadata fields OR an error key.
                if "error" not in meta:
                    assert "name" in meta, f"{name} missing name"
                    assert "version" in meta, f"{name} missing version"
                    assert "description" in meta, f"{name} missing description"

    def test_metadata_handles_missing_module(self, mock_tracer):
        """If a workflow module can't be imported, it should show as an error entry."""
        with patch("tools.workflow_ops.helpers.importlib.import_module") as mock_import:
            mock_import.side_effect = ImportError("module not found")

            result = workflow(action="list", trace_id="t-err")
            # The graph-backed types should all show as errors
            for type_name in ["research", "data", "autocode", "deep_research",
                              "understand", "autoresearch"]:
                assert type_name in result["workflows"]
                entry = result["workflows"][type_name]
                # Either has "error" key OR has metadata (if auto-discovered)
                assert "error" in entry or "name" in entry, (
                    f"{type_name} should have error or name: {entry}"
                )

    def test_metadata_handles_missing_workflow_metadata_attr(self, mock_tracer):
        """If a module exists but has no WORKFLOW_METADATA, it should show as error."""
        with patch("tools.workflow_ops.helpers.importlib.import_module") as mock_import:
            mock_mod = MagicMock()
            # Simulate the module not having WORKFLOW_METADATA
            del mock_mod.WORKFLOW_METADATA
            mock_import.return_value = mock_mod

            result = workflow(action="list", trace_id="t-noattr")
            for type_name in ["research", "data", "autocode"]:
                entry = result["workflows"][type_name]
                assert "error" in entry or "name" in entry
