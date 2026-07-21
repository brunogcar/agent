"""tests/workflows/understand/test_health.py

[v1.5] Tests for workflows.understand_impl.query.health_check — the index
health stats endpoint.

Covers:
  - Not indexed (kg.db missing) → indexed=False, all counts 0, success.
  - Indexed → indexed=True, file_count > 0, edge_count > 0, last_indexed > 0.
  - project_id is in the response.
  - kg_db_size_bytes > 0 when indexed.
  - embedding_available field is reflected from is_embedding_available().

[v1.5.1] Import path changed from `workflows.understand_query` to
`workflows.understand_impl.query` (module move).
"""
from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from core.kgraph.project import ProjectManager
from core.kgraph.storage import GraphStore
from workflows.understand_impl.query import health_check


# ─── Helpers ────────────────────────────────────────────────────────────────

def _setup_indexed_project(tmp_path, project_name, edges=None, files=None):
    """Create a project + ensure_initialized + insert file nodes + edges."""
    project_path = tmp_path / project_name
    (project_path / "code").mkdir(parents=True)
    pm = ProjectManager(project_path, is_agent_root=False)
    pm.ensure_initialized()
    store = GraphStore(pm.artifact_root / "kg.db")
    # Always insert at least one file node so file_count > 0.
    file_list = files or ["src/main.py", "src/utils.py"]
    for fp in file_list:
        targets = []
        if edges and fp in edges:
            targets = edges[fp]
        store.upsert_file_graph(pm.project_id, fp, "hash123", targets, 0.0, 100)
    store.close()
    return project_path


# ─── TestHealthCheck ────────────────────────────────────────────────────────

class TestHealthCheck:
    """[v1.5] health_check returns index stats without running the graph."""

    def test_health_not_indexed(self, tmp_path):
        """Project with no kg.db → indexed=False, all counts 0, status=success.

        This is NOT a failure — operators use health_check to DECIDE whether
        to index. Returns success with zeroed counts.
        """
        project_path = tmp_path / "unindexed"
        (project_path / "code").mkdir(parents=True)
        # Don't call ensure_initialized — no kg.db.

        # Mock is_embedding_available to avoid hitting LM Studio.
        with patch("core.kgraph.embeddings.is_embedding_available", return_value=False):
            result = health_check(
                project_path=str(project_path),
                trace_id="test-health-noidx",
            )
        assert result["status"] == "success"
        assert result["action"] == "health"
        assert result["indexed"] is False
        assert result["file_count"] == 0
        assert result["edge_count"] == 0
        assert result["vector_count"] == 0
        assert result["kg_db_size_bytes"] == 0
        assert result["chroma_dir_size_bytes"] == 0
        assert result["last_indexed"] == 0.0
        assert result["embedding_available"] is False
        assert result["errors"] == []

    def test_health_indexed(self, tmp_path):
        """Indexed project → indexed=True, file_count > 0, edge_count > 0."""
        project_path = _setup_indexed_project(
            tmp_path, "indexed_proj",
            edges={"src/main.py": ["src/utils.py"]},
            files=["src/main.py", "src/utils.py"],
        )

        with patch("core.kgraph.embeddings.is_embedding_available", return_value=True):
            result = health_check(
                project_path=str(project_path),
                trace_id="test-health-idx",
            )
        assert result["status"] == "success"
        assert result["indexed"] is True
        assert result["file_count"] >= 2  # at least main.py + utils.py
        assert result["edge_count"] >= 1  # main → utils edge
        assert result["last_indexed"] > 0  # kg.db mtime is a real timestamp

    def test_health_returns_project_id(self, tmp_path):
        """project_id is always in the response (even when not indexed)."""
        project_path = tmp_path / "pid_proj"
        (project_path / "code").mkdir(parents=True)

        with patch("core.kgraph.embeddings.is_embedding_available", return_value=False):
            result = health_check(
                project_path=str(project_path),
                trace_id="test-health-pid",
            )
        assert "project_id" in result
        # project_id is a 16-char hex string (sha256[:16] of the resolved path).
        assert len(result["project_id"]) == 16
        assert all(c in "0123456789abcdef" for c in result["project_id"])

    def test_health_kg_db_size(self, tmp_path):
        """kg_db_size_bytes > 0 when indexed (kg.db has content)."""
        project_path = _setup_indexed_project(
            tmp_path, "size_proj", files=["a.py", "b.py", "c.py"]
        )

        with patch("core.kgraph.embeddings.is_embedding_available", return_value=False):
            result = health_check(
                project_path=str(project_path),
                trace_id="test-health-size",
            )
        assert result["status"] == "success"
        assert result["indexed"] is True
        assert result["kg_db_size_bytes"] > 0

    def test_health_embedding_available(self, tmp_path):
        """embedding_available field reflects is_embedding_available() result."""
        project_path = _setup_indexed_project(tmp_path, "emb_proj", files=["x.py"])

        # When is_embedding_available returns True, the field must be True.
        with patch("core.kgraph.embeddings.is_embedding_available", return_value=True):
            result_true = health_check(
                project_path=str(project_path),
                trace_id="test-health-emb-true",
            )
        assert result_true["embedding_available"] is True

        # When it returns False, the field must be False.
        with patch("core.kgraph.embeddings.is_embedding_available", return_value=False):
            result_false = health_check(
                project_path=str(project_path),
                trace_id="test-health-emb-false",
            )
        assert result_false["embedding_available"] is False
