"""tests/workflows/understand/test_report.py

[v1.4.1 P2-4] Tests for node_report:
  - Summary must include vectors_created when embeddings were attempted.
  - Summary must omit the Vectors line when skip_embeddings=True.
  - Errors section is included when there are errors.
"""
from __future__ import annotations

from unittest.mock import patch, MagicMock


class TestReportSummary:
    """[v1.4.1 P2-4] Report summary must include vectors_created."""

    def _run_report(self, state):
        from workflows.understand_impl.nodes.report import node_report
        # Mock the report tool so it doesn't actually generate anything.
        with patch("tools.report.report") as mock_report:
            mock_report.return_value = {"status": "ok"}
            node_report(state)
            # Return the sections that were passed to the report tool.
            call_kwargs = mock_report.call_args[1]
            return call_kwargs["config"]["sections"]

    def test_summary_includes_vectors_when_not_skipped(self):
        """When skip_embeddings is False, the summary must include vectors_created."""
        state = {
            "project_path": "/tmp/test",
            "files_parsed": 10,
            "edges_created": 25,
            "vectors_created": 50,
            "skip_embeddings": False,
            "errors": [],
            "trace_id": "t1",
        }
        sections = self._run_report(state)
        summary_section = next(s for s in sections if s["title"] == "Indexing Summary")
        assert "Vectors created" in summary_section["content"]
        assert "50" in summary_section["content"]

    def test_summary_omits_vectors_when_skipped(self):
        """When skip_embeddings is True, the summary must NOT include vectors_created.

        Otherwise the operator sees a misleading "0 vectors" line that actually
        means "we didn't even try".
        """
        state = {
            "project_path": "/tmp/test",
            "files_parsed": 10,
            "edges_created": 25,
            "vectors_created": 0,
            "skip_embeddings": True,
            "errors": [],
            "trace_id": "t1",
        }
        sections = self._run_report(state)
        summary_section = next(s for s in sections if s["title"] == "Indexing Summary")
        assert "Vectors created" not in summary_section["content"]

    def test_summary_includes_files_and_edges(self):
        """Summary must always include Files parsed + Edges created."""
        state = {
            "project_path": "/tmp/test",
            "files_parsed": 42,
            "edges_created": 156,
            "vectors_created": 0,
            "skip_embeddings": True,
            "errors": [],
            "trace_id": "t1",
        }
        sections = self._run_report(state)
        summary_section = next(s for s in sections if s["title"] == "Indexing Summary")
        assert "Files parsed" in summary_section["content"]
        assert "42" in summary_section["content"]
        assert "Edges created" in summary_section["content"]
        assert "156" in summary_section["content"]

    def test_errors_section_present_when_errors_exist(self):
        """An Errors section must be added when the errors list is non-empty."""
        state = {
            "project_path": "/tmp/test",
            "files_parsed": 5,
            "edges_created": 10,
            "vectors_created": 0,
            "skip_embeddings": True,
            "errors": ["Failed to parse broken.py: SyntaxError: ..."],
            "trace_id": "t1",
        }
        sections = self._run_report(state)
        error_section = next((s for s in sections if s["title"] == "Errors"), None)
        assert error_section is not None, "Errors section must be present when errors exist"
        assert "broken.py" in error_section["content"]
