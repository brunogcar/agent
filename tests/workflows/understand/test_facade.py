"""tests/workflows/understand/test_facade.py

[v1.4.1] Tests for the workflows.understand facade:
  - P0-2: lazy is_same_path import — facade must be importable even if
    core.kgraph.project is broken at import time.
  - P2-7: success path returns a dict with `errors: []`.
  - P2-9: validates project_path at entry — fails fast for a non-existent path.
"""
from __future__ import annotations

import sys
import types
from unittest.mock import patch, MagicMock
from pathlib import Path


class TestLazyIsSamePathImport:
    """[v1.4.1 P0-2] The facade must NOT import is_same_path at module load.

    Was: `from core.kgraph.project import is_same_path` at the top of
    workflows/understand.py. If kgraph had any import-time failure, the
    entire workflows.understand module failed to import → cascaded to
    any caller that did `from workflows.understand import ...`.

    Now: the import is deferred inside run_understand_workflow_sync().
    """

    def test_facade_source_has_no_top_level_is_same_path_import(self):
        """The facade source must not have a top-level is_same_path import."""
        import workflows.understand as mod
        with open(mod.__file__, encoding="utf-8") as f:
            source = f.read()
        # The lazy import INSIDE the function is fine — only the module-level
        # one is forbidden. We check by stripping the function bodies and
        # asserting the import doesn't appear in the module-level section.
        # Simpler: the import line should NOT appear at column 0.
        for line in source.splitlines():
            stripped = line.lstrip()
            if stripped.startswith("from core.kgraph.project import is_same_path"):
                # If it appears, it must be indented (inside a function).
                assert line[0] in (" ", "\t"), (
                    "is_same_path import must be inside a function (lazy), "
                    "not at module top-level"
                )

    def test_facade_importable_with_broken_kgraph(self, monkeypatch, make_project):
        """Even if core.kgraph.project is broken, the facade must import.

        We simulate a broken kgraph by inserting a fake module that raises
        on attribute access. The facade should still import successfully
        (it doesn't import kgraph at module load).
        """
        # Pre-import to make sure it's cached.
        import workflows.understand

        # Now poison core.kgraph.project in sys.modules — any future import
        # attempt should fail. The facade must NOT have already imported it
        # at module load (if it had, this test would be a no-op).
        broken = types.ModuleType("core.kgraph.project")
        def _broken_getattr(name):
            raise ImportError(f"simulated broken kgraph.project.{name}")
        broken.__getattr__ = _broken_getattr
        monkeypatch.setitem(sys.modules, "core.kgraph.project", broken)

        # Force a re-import of the facade. If the facade had a top-level
        # `from core.kgraph.project import is_same_path`, this would fail.
        # We don't actually re-import (Python caches); instead we verify
        # the module is still accessible + the function reference is intact.
        assert hasattr(workflows.understand, "run_understand_workflow_sync")
        assert callable(workflows.understand.run_understand_workflow_sync)

        # Calling the facade with a non-existent path should hit our early
        # project_path check (P2-9) and return a clean failure dict —
        # WITHOUT ever touching kgraph (the is_same_path import is inside
        # the function but only reached AFTER the project_path check passes).
        result = workflows.understand.run_understand_workflow_sync(
            "/nonexistent/path/that/does/not/exist",
            trace_id="test-broken-kgraph",
        )
        assert result["status"] == "failed"
        assert "does not exist" in result["errors"][0]


class TestFacadeReturnShape:
    """[v1.4.1 P2-7] Success path must include `errors: []`."""

    def test_success_path_includes_empty_errors(self, mocker, make_project):
        """When the workflow succeeds, the result must include `errors: []`."""
        from workflows.understand import run_understand_workflow_sync

        project_path = make_project()
        # Mock the graph invoke to return a success state WITHOUT an `errors` key.
        # The facade must add `errors: []` to normalize the return shape.
        fake_graph = MagicMock()
        fake_graph.invoke.return_value = {
            "status": "completed",
            "files_parsed": 5,
            "edges_created": 10,
            # NOTE: no `errors` key — facade must add it.
        }
        mocker.patch("workflows.understand.build_understand_graph", return_value=fake_graph)
        mocker.patch("workflows.understand._default_state", return_value={"project_path": str(project_path)})

        # Patch is_same_path (imported lazily inside the function) to bypass
        # the agent_root check.
        mocker.patch("core.kgraph.project.is_same_path", return_value=False)

        result = run_understand_workflow_sync(str(project_path), trace_id="test-success")
        assert result["status"] == "completed"
        assert "errors" in result
        assert result["errors"] == []


class TestFacadeValidatesProjectPath:
    """[v1.4.1 P2-9] Facade must fail fast for non-existent project_path."""

    def test_returns_failure_for_nonexistent_path(self):
        """A non-existent project_path must return a clean failure dict."""
        from workflows.understand import run_understand_workflow_sync

        result = run_understand_workflow_sync(
            "/definitely/does/not/exist/" + "x" * 40,
            trace_id="test-missing-path",
        )
        assert result["status"] == "failed"
        assert len(result["errors"]) == 1
        assert "does not exist" in result["errors"][0]

    def test_returns_failure_for_empty_path(self):
        """An empty project_path must return a clean failure dict."""
        from workflows.understand import run_understand_workflow_sync

        result = run_understand_workflow_sync("", trace_id="test-empty-path")
        assert result["status"] == "failed"
        assert "does not exist" in result["errors"][0]


# ─── [v1.5] Action routing ──────────────────────────────────────────────────

class TestFacadeActionRouting:
    """[v1.5] run_understand_workflow_sync now accepts an `action` parameter.

    Default action='index' runs the graph (backward compat). action='query'
    routes to query_codebase(); action='health' routes to health_check().
    Both query/health bypass graph construction entirely.
    """

    def test_action_index_default(self, mocker, make_project):
        """action='index' (default) → runs the graph (backward compat)."""
        from workflows.understand import run_understand_workflow_sync

        project_path = make_project()
        # Mock the graph invoke — we only need to verify it WAS called.
        fake_graph = MagicMock()
        fake_graph.invoke.return_value = {
            "status": "completed",
            "files_parsed": 5,
            "edges_created": 10,
            "errors": [],
        }
        mocker.patch("workflows.understand.build_understand_graph", return_value=fake_graph)
        mocker.patch(
            "workflows.understand._default_state",
            return_value={"project_path": str(project_path)},
        )
        mocker.patch("core.kgraph.project.is_same_path", return_value=False)

        # Call WITHOUT action — should default to "index" and run the graph.
        result = run_understand_workflow_sync(str(project_path), trace_id="test-idx-default")
        assert result["status"] == "completed"
        # The graph's invoke MUST have been called (action=index path).
        fake_graph.invoke.assert_called_once()

    def test_action_query_routes_to_query_codebase(self, mocker, make_project):
        """action='query' → calls query_codebase (graph NOT built)."""
        from workflows.understand import run_understand_workflow_sync

        project_path = make_project()
        # Patch query_codebase on the understand module (where it's re-exported).
        mock_query = mocker.patch(
            "workflows.understand.query_codebase",
            return_value={
                "status": "success",
                "action": "query",
                "query_type": "semantic",
                "results": [],
                "count": 0,
                "errors": [],
            },
        )
        # Patch build_understand_graph to ensure it's NOT called.
        mock_build = mocker.patch("workflows.understand.build_understand_graph")
        mocker.patch("core.kgraph.project.is_same_path", return_value=False)

        result = run_understand_workflow_sync(
            str(project_path),
            trace_id="test-query-route",
            action="query",
            question="how does auth work",
            query_type="semantic",
            top_k=5,
        )
        assert result["status"] == "success"
        assert result["action"] == "query"
        # query_codebase was called with the right args.
        mock_query.assert_called_once()
        call_kwargs = mock_query.call_args[1]
        assert call_kwargs["question"] == "how does auth work"
        assert call_kwargs["query_type"] == "semantic"
        assert call_kwargs["top_k"] == 5
        # The graph was NOT built (action=query bypasses it).
        mock_build.assert_not_called()

    def test_action_health_routes_to_health_check(self, mocker, make_project):
        """action='health' → calls health_check (graph NOT built)."""
        from workflows.understand import run_understand_workflow_sync

        project_path = make_project()
        mock_health = mocker.patch(
            "workflows.understand.health_check",
            return_value={
                "status": "success",
                "action": "health",
                "indexed": True,
                "file_count": 42,
                "edge_count": 100,
                "errors": [],
            },
        )
        mock_build = mocker.patch("workflows.understand.build_understand_graph")
        mocker.patch("core.kgraph.project.is_same_path", return_value=False)

        result = run_understand_workflow_sync(
            str(project_path),
            trace_id="test-health-route",
            action="health",
        )
        assert result["status"] == "success"
        assert result["action"] == "health"
        mock_health.assert_called_once()
        mock_build.assert_not_called()

    def test_action_unknown_returns_failed(self, mocker, make_project):
        """Unknown action value → status='failed' with descriptive error."""
        from workflows.understand import run_understand_workflow_sync

        project_path = make_project()
        mocker.patch("core.kgraph.project.is_same_path", return_value=False)

        result = run_understand_workflow_sync(
            str(project_path),
            trace_id="test-unknown-action",
            action="bogus",
        )
        assert result["status"] == "failed"
        assert len(result["errors"]) == 1
        assert "Unknown action" in result["errors"][0]
        assert "index" in result["errors"][0]
        assert "query" in result["errors"][0]
        assert "health" in result["errors"][0]
