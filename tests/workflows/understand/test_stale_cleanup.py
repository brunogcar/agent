"""tests/workflows/understand/test_stale_cleanup.py

[v1.6] Tests for the stale-index cleanup phase added to
node_discover_files. When a file is indexed but later deleted from disk,
its graph node + edges + vectors must be removed (was: orphaned forever).

Six test cases:
  1. Stale file's node is deleted from GraphStore.
  2. Stale file's outgoing + incoming edges are deleted.
  3. Stale file's vectors are deleted from ChromaDB.
  4. No stale files → no cleanup trace message.
  5. skip_embeddings=True → ChromaDB collection.delete NOT called
     (but GraphStore cleanup still happens).
  6. Trace message includes the count of cleaned-up files.
"""
from __future__ import annotations

from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from core.kgraph.project import ProjectManager
from core.kgraph.storage import GraphStore
from workflows.understand_impl.nodes.discover_files import node_discover_files


# ─── Helpers ────────────────────────────────────────────────────────────────

def _setup_indexed_project(tmp_path, project_name, file_paths, edges=None):
    """Create a project + GraphStore + insert file nodes + edges.

    Returns (project_path, pm). The caller is expected to delete files
    from disk before re-running discover_files to trigger stale cleanup.
    """
    project_path = tmp_path / project_name
    (project_path / "code").mkdir(parents=True)
    pm = ProjectManager(project_path, is_agent_root=False)
    pm.ensure_initialized()
    # Create the files on disk so discover_files's Phase 1 walk sees them.
    for fp in file_paths:
        full = project_path / "code" / fp
        full.parent.mkdir(parents=True, exist_ok=True)
        full.write_text("# placeholder\n")
    # Index them in the store.
    store = GraphStore(pm.artifact_root / "kg.db")
    for fp in file_paths:
        targets = []
        if edges and fp in edges:
            targets = edges[fp]
        store.upsert_file_graph(pm.project_id, fp, "hash123", targets, 0.0, 100)
    store.close()
    return project_path, pm


def _make_state(project_path, trace_id="test-stale", skip_embeddings=False):
    return {
        "project_path": str(project_path),
        "is_agent_root": False,
        "project_id": "test-pid",
        "trace_id": trace_id,
        "status": "running",
        "skip_embeddings": skip_embeddings,
    }


# ─── TestStaleCleanup ──────────────────────────────────────────────────────

class TestStaleCleanup:
    """[v1.6] node_discover_files prunes graph entries for deleted files."""

    def test_stale_file_node_deleted(self, tmp_path):
        """Index 3 files, delete 1, re-run discover_files → that node is gone."""
        project_path, pm = _setup_indexed_project(
            tmp_path, "stale_node",
            ["src/main.py", "src/utils.py", "src/auth.py"],
        )
        # Delete utils.py from disk.
        (project_path / "code" / "src" / "utils.py").unlink()
        # Sanity: file is gone from disk.
        assert not (project_path / "code" / "src" / "utils.py").exists()

        # Build state — project_id from PM so the queries match the store.
        state = _make_state(project_path)
        state["project_id"] = pm.project_id

        node_discover_files(state)

        # Verify: utils.py's node is gone; main.py + auth.py still there.
        store = GraphStore(pm.artifact_root / "kg.db")
        all_paths = set(store.get_all_file_paths(pm.project_id))
        store.close()
        assert "src/utils.py" not in all_paths, (
            "stale file's node should be deleted from GraphStore"
        )
        assert "src/main.py" in all_paths
        assert "src/auth.py" in all_paths

    def test_stale_file_edges_deleted(self, tmp_path):
        """Edges (outgoing + incoming) for the deleted file are gone too."""
        project_path, pm = _setup_indexed_project(
            tmp_path, "stale_edges",
            ["src/main.py", "src/utils.py", "src/auth.py"],
            edges={
                # main imports utils + auth → outgoing edges from main.
                "src/main.py": ["src/utils.py", "src/auth.py"],
                # auth imports utils → outgoing edge from auth, incoming to utils.
                "src/auth.py": ["src/utils.py"],
            },
        )
        # Delete utils.py from disk → its incoming edges (from main + auth)
        # should be deleted. Outgoing edges from utils don't exist (it had none).
        (project_path / "code" / "src" / "utils.py").unlink()

        state = _make_state(project_path)
        state["project_id"] = pm.project_id

        node_discover_files(state)

        store = GraphStore(pm.artifact_root / "kg.db")
        # utils.py's node id — verify NO edges target it.
        utils_node_id = "file:src/utils.py"
        incoming = store.read(
            "SELECT source_id FROM edges WHERE project_id = ? AND target_id = ?",
            (pm.project_id, "src/utils.py"),
        )
        incoming_by_node_id = store.read(
            "SELECT source_id FROM edges WHERE project_id = ? AND target_id = ?",
            (pm.project_id, utils_node_id),
        )
        # And no edges source from utils.
        outgoing = store.read(
            "SELECT target_id FROM edges WHERE project_id = ? AND source_id = ?",
            (pm.project_id, utils_node_id),
        )
        store.close()

        assert len(incoming) == 0, (
            f"incoming edges (target_id=path) for stale file should be deleted; "
            f"got {[dict(r) for r in incoming]}"
        )
        assert len(incoming_by_node_id) == 0, (
            f"incoming edges (target_id=file:path) for stale file should be deleted"
        )
        assert len(outgoing) == 0, (
            f"outgoing edges for stale file should be deleted"
        )

    def test_stale_file_vectors_deleted(self, mocker, tmp_path):
        """ChromaDB collection.delete is called for each orphan path."""
        project_path, pm = _setup_indexed_project(
            tmp_path, "stale_vecs",
            ["src/main.py", "src/utils.py"],
        )
        (project_path / "code" / "src" / "utils.py").unlink()

        # Mock the ChromaDB collection so we can observe .delete() calls.
        mock_collection = MagicMock()
        mocker.patch(
            "core.kgraph.vectors.get_project_vector_collection",
            return_value=mock_collection,
        )

        state = _make_state(project_path, skip_embeddings=False)
        state["project_id"] = pm.project_id

        node_discover_files(state)

        # Verify collection.delete was called with utils.py.
        delete_calls = [c.kwargs.get("where") for c in mock_collection.delete.call_args_list]
        assert {"file_path": "src/utils.py"} in delete_calls, (
            f"ChromaDB delete should be called for orphan path 'src/utils.py'; "
            f"got: {delete_calls}"
        )
        # main.py was NOT deleted — it still exists on disk.
        assert {"file_path": "src/main.py"} not in delete_calls

    def test_no_stale_files_no_cleanup(self, mocker, tmp_path):
        """When no files were deleted, no cleanup trace message is emitted."""
        project_path, pm = _setup_indexed_project(
            tmp_path, "no_stale",
            ["src/main.py", "src/utils.py"],
        )
        # Don't delete anything — re-running discover should find no orphans.

        mock_collection = MagicMock()
        mocker.patch(
            "core.kgraph.vectors.get_project_vector_collection",
            return_value=mock_collection,
        )

        # Capture tracer.step calls to verify the "No stale files" message.
        step_calls: list[str] = []
        original_step = None

        from core.tracer import tracer
        def fake_step(tid, node, msg, **kwargs):
            step_calls.append(msg)

        mocker.patch.object(tracer, "step", side_effect=fake_step)

        state = _make_state(project_path)
        state["project_id"] = pm.project_id

        node_discover_files(state)

        # The "No stale files detected." message should be in the trace.
        assert any("No stale files detected" in m for m in step_calls), (
            f"expected 'No stale files detected' in trace, got: {step_calls}"
        )
        # And ChromaDB delete should NOT have been called.
        mock_collection.delete.assert_not_called()

    def test_stale_cleanup_skips_chroma_when_skip_embeddings(self, mocker, tmp_path):
        """skip_embeddings=True → GraphStore cleanup happens, ChromaDB does NOT."""
        project_path, pm = _setup_indexed_project(
            tmp_path, "stale_skip_emb",
            ["src/main.py", "src/utils.py"],
        )
        (project_path / "code" / "src" / "utils.py").unlink()

        mock_collection = MagicMock()
        mocker.patch(
            "core.kgraph.vectors.get_project_vector_collection",
            return_value=mock_collection,
        )

        state = _make_state(project_path, skip_embeddings=True)
        state["project_id"] = pm.project_id

        node_discover_files(state)

        # GraphStore cleanup still happened — utils.py's node is gone.
        store = GraphStore(pm.artifact_root / "kg.db")
        all_paths = set(store.get_all_file_paths(pm.project_id))
        store.close()
        assert "src/utils.py" not in all_paths, (
            "GraphStore cleanup should still happen even with skip_embeddings=True"
        )
        # But ChromaDB delete was NOT called.
        mock_collection.delete.assert_not_called()

    def test_stale_cleanup_traces_count(self, mocker, tmp_path):
        """The trace message includes the count of cleaned-up files."""
        project_path, pm = _setup_indexed_project(
            tmp_path, "stale_count",
            ["src/main.py", "src/utils.py", "src/auth.py"],
        )
        # Delete 2 files → count should be 2.
        (project_path / "code" / "src" / "utils.py").unlink()
        (project_path / "code" / "src" / "auth.py").unlink()

        mock_collection = MagicMock()
        mocker.patch(
            "core.kgraph.vectors.get_project_vector_collection",
            return_value=mock_collection,
        )

        step_calls: list[str] = []
        from core.tracer import tracer
        def fake_step(tid, node, msg, **kwargs):
            step_calls.append(msg)
        mocker.patch.object(tracer, "step", side_effect=fake_step)

        state = _make_state(project_path)
        state["project_id"] = pm.project_id

        node_discover_files(state)

        # Find the cleanup message + verify it includes the count.
        cleanup_msgs = [m for m in step_calls if "Cleaned up" in m and "stale" in m]
        assert len(cleanup_msgs) == 1, (
            f"expected exactly 1 cleanup trace message; got: {cleanup_msgs}"
        )
        assert "2" in cleanup_msgs[0], (
            f"cleanup message should include the count '2'; got: {cleanup_msgs[0]}"
        )
