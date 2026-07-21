"""tests/workflows/understand/test_discover_files.py

[v1.4.1] Tests for node_discover_files:
  - P1-1: defensive status=="failed" bail (returns {}).
  - P1-6: cancellation check at start + mid-walk.
  - P1-7: GraphStore created inside try; finally checks for None (no NameError
    if the constructor raises).
  - P2-2: uses ProjectManager.SKIP_DIRS (was: a local set).
"""
from __future__ import annotations

from unittest.mock import patch, MagicMock
from pathlib import Path


class TestDefensiveBailOnFailedStatus:
    """[v1.4.1 P1-1] If status=="failed", the node must return {} immediately."""

    def test_returns_empty_dict_when_status_failed(self, make_project):
        from workflows.understand_impl.nodes.discover_files import node_discover_files

        project_path = make_project()
        state = {
            "project_path": str(project_path),
            "is_agent_root": False,
            "project_id": "test",
            "trace_id": "t1",
            "status": "failed",
        }
        result = node_discover_files(state)
        assert result == {}


class TestCancellationCheck:
    """[v1.4.1 P1-6] Node must check is_workflow_cancelled at start + mid-walk."""

    def test_returns_failed_when_cancelled_at_start(self, mocker, make_project):
        from workflows.understand_impl.nodes.discover_files import node_discover_files

        project_path = make_project()
        mocker.patch(
            "workflows.base.is_workflow_cancelled",
            return_value=True,
        )
        state = {
            "project_path": str(project_path),
            "is_agent_root": False,
            "project_id": "test",
            "trace_id": "t1",
            "status": "running",
        }
        result = node_discover_files(state)
        assert result["status"] == "failed"
        assert "cancelled" in result["errors"][0].lower()


class TestGraphStoreInTry:
    """[v1.4.1 P1-7] GraphStore constructor failure must not crash with NameError.

    Was: `store = GraphStore(db_path)` BEFORE try; `finally: store.close()` raised
    NameError when the constructor itself raised, masking the original exception.
    Now: `store = None` before try; `if store is not None: store.close()` in finally.
    """

    def test_no_name_error_when_graphstore_constructor_raises(self, mocker, make_project):
        from workflows.understand_impl.nodes.discover_files import node_discover_files

        project_path = make_project()
        # Make the GraphStore constructor blow up.
        mocker.patch(
            "workflows.understand_impl.nodes.discover_files.GraphStore",
            side_effect=RuntimeError("simulated sqlite3 failure"),
        )
        state = {
            "project_path": str(project_path),
            "is_agent_root": False,
            "project_id": "test",
            "trace_id": "t1",
            "status": "running",
        }
        # Pre-v1.4.1 this would raise NameError("store") from the finally block.
        # v1.4.1 should propagate the original RuntimeError cleanly.
        try:
            node_discover_files(state)
            raised = None
        except Exception as e:
            raised = e
        # The RuntimeError should propagate (we don't catch it inside the node).
        # The important thing is it's NOT NameError.
        assert raised is not None
        assert not isinstance(raised, NameError), (
            "P1-7: GraphStore constructor failure must not raise NameError from finally"
        )


class TestSkipDirsConstant:
    """[v1.4.1 P2-2] ProjectManager.SKIP_DIRS includes the new common skip dirs."""

    def test_skip_dirs_includes_mypy_cache(self):
        from core.kgraph.project import ProjectManager
        assert ".mypy_cache" in ProjectManager.SKIP_DIRS

    def test_skip_dirs_includes_ruff_cache(self):
        from core.kgraph.project import ProjectManager
        assert ".ruff_cache" in ProjectManager.SKIP_DIRS

    def test_skip_dirs_includes_tox(self):
        from core.kgraph.project import ProjectManager
        assert ".tox" in ProjectManager.SKIP_DIRS

    def test_skip_dirs_includes_htmlcov(self):
        from core.kgraph.project import ProjectManager
        assert "htmlcov" in ProjectManager.SKIP_DIRS

    def test_skip_dirs_is_frozenset(self):
        from core.kgraph.project import ProjectManager
        assert isinstance(ProjectManager.SKIP_DIRS, frozenset)

    def test_skip_dirs_preserves_v1_3_entries(self):
        """The v1.3 entries must still be present (no regression)."""
        from core.kgraph.project import ProjectManager
        for required in ("node_modules", "__pycache__", ".git", ".venv", "venv",
                         ".understand", "dist", "build", ".pytest_cache"):
            assert required in ProjectManager.SKIP_DIRS, (
                f"v1.3 skip_dir entry missing: {required}"
            )
