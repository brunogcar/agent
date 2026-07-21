"""tests/workflows/understand/test_query.py

[v1.5] Tests for workflows.understand_impl.query.query_codebase — the
unified query interface that routes to semantic / keyword / dependencies /
callers based on the `query_type` parameter.

Each test class covers one query_type + the error paths (invalid type,
missing file_path, not indexed, graceful degradation).

[v1.5.1] Import path changed from `workflows.understand_query` to
`workflows.understand_impl.query` (module move).
"""
from __future__ import annotations

from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from core.kgraph.project import ProjectManager
from core.kgraph.storage import GraphStore
from workflows.understand_impl.query import query_codebase


# ─── Helpers ────────────────────────────────────────────────────────────────

def _setup_project_with_edges(tmp_path, project_name, edges):
    """Create a project + GraphStore + insert the given edges.

    Mirrors the helper in tests/core/kgraph/test_queries.py — same shape
    so the dependency/caller tests are easy to reason about.

    edges: list of (source_rel_path, [target_id, target_id, ...])
    """
    project_path = tmp_path / project_name
    (project_path / "code").mkdir(parents=True)
    pm = ProjectManager(project_path, is_agent_root=False)
    pm.ensure_initialized()
    store = GraphStore(pm.artifact_root / "kg.db")
    for source_rel, targets in edges:
        store.upsert_file_graph(pm.project_id, source_rel, "hash123", targets, 0.0, 100)
    store.close()
    return project_path


def _setup_project_with_files(tmp_path, project_name, file_paths):
    """Create a project + GraphStore + insert file nodes (no edges)."""
    project_path = tmp_path / project_name
    (project_path / "code").mkdir(parents=True)
    pm = ProjectManager(project_path, is_agent_root=False)
    pm.ensure_initialized()
    store = GraphStore(pm.artifact_root / "kg.db")
    for fp in file_paths:
        store.upsert_file_graph(pm.project_id, fp, "hash123", [], 0.0, 100)
    store.close()
    return project_path


# ─── TestQuerySemantic ─────────────────────────────────────────────────────

class TestQuerySemantic:
    """query_type='semantic' → query_similar_code + snippet formatting."""

    def test_semantic_search_returns_results(self, mocker, tmp_path):
        """Semantic search returns results with all expected fields."""
        project_path = _setup_project_with_files(tmp_path, "sem_proj", ["core/config.py"])

        # Mock is_embedding_available so the early-degradation path doesn't fire.
        mocker.patch(
            "core.kgraph.embeddings.is_embedding_available", return_value=True
        )
        # Mock query_similar_code to return a fake result.
        fake_result = [{
            "file_path": "core/config.py",
            "name": "load_config",
            "type": "function",
            "line_start": 10,
            "line_end": 15,
            "distance": 0.123,
            "source": "def load_config():\n    return {'key': 'value'}\n",
        }]
        mocker.patch(
            "core.kgraph.vectors.query_similar_code", return_value=fake_result
        )

        result = query_codebase(
            project_path=str(project_path),
            question="how does config load",
            query_type="semantic",
            top_k=5,
            trace_id="test-sem-1",
        )
        assert result["status"] == "success"
        assert result["action"] == "query"
        assert result["query_type"] == "semantic"
        assert result["count"] == 1
        r = result["results"][0]
        # All required fields present.
        assert r["file_path"] == "core/config.py"
        assert r["name"] == "load_config"
        assert r["type"] == "function"
        assert r["line_start"] == 10
        assert r["line_end"] == 15
        assert r["distance"] == 0.123
        assert "source" in r
        # Snippet was added by query_codebase.
        assert "snippet" in r

    def test_semantic_search_snippet_has_line_numbers(self, mocker, tmp_path):
        """The snippet field uses `  N | ` grep -n style line prefixes."""
        project_path = _setup_project_with_files(tmp_path, "sem_snip", ["app.py"])

        mocker.patch(
            "core.kgraph.embeddings.is_embedding_available", return_value=True
        )
        # Source starts at line 10 (line_start=10). The snippet should number
        # lines starting at 10, not 1.
        fake_result = [{
            "file_path": "app.py",
            "name": "foo",
            "type": "function",
            "line_start": 10,
            "line_end": 11,
            "distance": 0.05,
            "source": "def foo():\n    return 42\n",
        }]
        mocker.patch(
            "core.kgraph.vectors.query_similar_code", return_value=fake_result
        )

        result = query_codebase(
            project_path=str(project_path),
            question="foo",
            query_type="semantic",
            trace_id="test-sem-snip",
        )
        snippet = result["results"][0]["snippet"]
        # First line should be " 10 | def foo():" — grep -n style with the
        # line_start offset (10, not 1).
        assert "10 | def foo():" in snippet
        # Second line should be " 11 |     return 42".
        assert "11 |     return 42" in snippet

    def test_semantic_search_graceful_degradation(self, mocker, tmp_path):
        """When is_embedding_available() returns False, return success with
        empty results + a descriptive error (NOT a hard failure).

        Lets callers fall back to keyword search without an extra round-trip.
        """
        project_path = _setup_project_with_files(tmp_path, "sem_deg", ["x.py"])

        mocker.patch(
            "core.kgraph.embeddings.is_embedding_available", return_value=False
        )
        # query_similar_code should NOT be called (early return).
        mock_query = mocker.patch("core.kgraph.vectors.query_similar_code")

        result = query_codebase(
            project_path=str(project_path),
            question="anything",
            query_type="semantic",
            trace_id="test-sem-deg",
        )
        assert result["status"] == "success"
        assert result["count"] == 0
        assert result["results"] == []
        assert len(result["errors"]) == 1
        assert "Embedding service unavailable" in result["errors"][0]
        mock_query.assert_not_called()

    def test_semantic_search_not_indexed(self, tmp_path):
        """Querying a project with no kg.db → status='failed' with hint."""
        # Create a project dir but DON'T call ensure_initialized (no kg.db).
        project_path = tmp_path / "unindexed"
        (project_path / "code").mkdir(parents=True)

        result = query_codebase(
            project_path=str(project_path),
            question="anything",
            query_type="semantic",
            trace_id="test-sem-noidx",
        )
        assert result["status"] == "failed"
        assert len(result["errors"]) == 1
        assert "not indexed" in result["errors"][0].lower()
        assert "kg.db" in result["errors"][0]


# ─── TestQueryKeyword ──────────────────────────────────────────────────────

class TestQueryKeyword:
    """query_type='keyword' → find_relevant_files (SQL path match)."""

    def test_keyword_search_returns_file_paths(self, tmp_path):
        """Keyword search returns file paths whose names match the query."""
        # File paths that contain 'auth' and 'config'.
        project_path = _setup_project_with_files(
            tmp_path, "kw_proj",
            ["src/auth.py", "core/config.py", "README.md"],
        )

        result = query_codebase(
            project_path=str(project_path),
            question="auth config",
            query_type="keyword",
            top_k=5,
            trace_id="test-kw-1",
        )
        assert result["status"] == "success"
        assert result["query_type"] == "keyword"
        assert result["count"] >= 1
        # Results are dicts with file_path (uniform shape across query types).
        paths = [r["file_path"] for r in result["results"]]
        assert "src/auth.py" in paths
        assert "core/config.py" in paths
        # README.md shouldn't match "auth config".
        assert "README.md" not in paths

    def test_keyword_search_no_matches(self, tmp_path):
        """A query that matches no file → empty results, status='success'."""
        project_path = _setup_project_with_files(
            tmp_path, "kw_nomatch",
            ["src/auth.py", "core/config.py"],
        )

        result = query_codebase(
            project_path=str(project_path),
            question="zzz_nonexistent_zzz",
            query_type="keyword",
            trace_id="test-kw-nomatch",
        )
        assert result["status"] == "success"
        assert result["count"] == 0
        assert result["results"] == []


# ─── TestQueryDependencies ─────────────────────────────────────────────────

class TestQueryDependencies:
    """query_type='dependencies' → get_dependencies (outgoing edges)."""

    def test_dependencies_returns_outgoing_edges(self, tmp_path):
        """File A imports file B → B appears in A's dependencies."""
        project_path = _setup_project_with_edges(
            tmp_path, "dep_proj",
            [("src/main.py", ["src/utils.py", "src/auth.py"])],
        )

        result = query_codebase(
            project_path=str(project_path),
            question="",  # ignored for dependencies
            query_type="dependencies",
            file_path="src/main.py",
            trace_id="test-dep-1",
        )
        assert result["status"] == "success"
        assert result["query_type"] == "dependencies"
        targets = [r["target"] for r in result["results"]]
        assert "src/utils.py" in targets
        assert "src/auth.py" in targets

    def test_dependencies_requires_file_path(self, tmp_path):
        """Calling dependencies without file_path → status='failed'."""
        project_path = _setup_project_with_edges(
            tmp_path, "dep_nofile",
            [("src/main.py", ["src/utils.py"])],
        )

        result = query_codebase(
            project_path=str(project_path),
            question="",
            query_type="dependencies",
            file_path="",  # missing
            trace_id="test-dep-nofile",
        )
        assert result["status"] == "failed"
        assert len(result["errors"]) == 1
        assert "file_path is required" in result["errors"][0]


# ─── TestQueryCallers ──────────────────────────────────────────────────────

class TestQueryCallers:
    """query_type='callers' → get_callers (incoming edges)."""

    def test_callers_returns_incoming_edges(self, tmp_path):
        """File A imports file B → A appears in B's callers."""
        project_path = _setup_project_with_edges(
            tmp_path, "call_proj",
            [("src/main.py", ["src/utils.py"])],  # main imports utils
        )

        result = query_codebase(
            project_path=str(project_path),
            question="",
            query_type="callers",
            file_path="src/utils.py",
            trace_id="test-call-1",
        )
        assert result["status"] == "success"
        assert result["query_type"] == "callers"
        callers = [r["caller"] for r in result["results"]]
        assert "src/main.py" in callers

    def test_callers_requires_file_path(self, tmp_path):
        """Calling callers without file_path → status='failed'."""
        project_path = _setup_project_with_edges(
            tmp_path, "call_nofile",
            [("src/main.py", ["src/utils.py"])],
        )

        result = query_codebase(
            project_path=str(project_path),
            question="",
            query_type="callers",
            file_path="",
            trace_id="test-call-nofile",
        )
        assert result["status"] == "failed"
        assert len(result["errors"]) == 1
        assert "file_path is required" in result["errors"][0]


# ─── TestQueryInvalidType ──────────────────────────────────────────────────

class TestQueryInvalidType:
    """Invalid query_type → status='failed' with descriptive error."""

    def test_invalid_query_type_returns_failed(self, tmp_path):
        project_path = _setup_project_with_files(tmp_path, "inv_proj", ["x.py"])

        result = query_codebase(
            project_path=str(project_path),
            question="anything",
            query_type="invalid_type",
            trace_id="test-invalid",
        )
        assert result["status"] == "failed"
        assert len(result["errors"]) == 1
        assert "Invalid query_type" in result["errors"][0]
        # Error message should list the valid types so the caller can fix it.
        assert "semantic" in result["errors"][0]
        assert "keyword" in result["errors"][0]
        assert "dependencies" in result["errors"][0]
        assert "callers" in result["errors"][0]
