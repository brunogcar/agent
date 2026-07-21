"""tests/workflows/understand/test_doc_indexing.py

v1.3: Tests for .md/.txt/.rst document indexing via chonkie.

Tests:
  - DOC_EXTENSIONS includes .md, .txt, .rst
  - ALL_SUPPORTED_EXTENSIONS = code + doc
  - is_doc_file() correctly identifies doc files
  - extract_doc_chunks() returns proper dict shape
  - extract_doc_chunks() falls back to single chunk when chonkie missing
  - parse_and_store branches correctly for doc vs code files
"""
from __future__ import annotations

from unittest.mock import patch, MagicMock, ANY
from pathlib import Path


class TestDocExtensions:
    """v1.3: DOC_EXTENSIONS + ALL_SUPPORTED_EXTENSIONS in tree_sitter_parser."""

    def test_doc_extensions_includes_md_txt_rst(self):
        from core.kgraph.tree_sitter_parser import DOC_EXTENSIONS
        assert ".md" in DOC_EXTENSIONS
        assert ".txt" in DOC_EXTENSIONS
        assert ".rst" in DOC_EXTENSIONS

    def test_all_supported_extensions_is_union(self):
        from core.kgraph.tree_sitter_parser import ALL_SUPPORTED_EXTENSIONS, SUPPORTED_EXTENSIONS, DOC_EXTENSIONS
        assert ALL_SUPPORTED_EXTENSIONS == SUPPORTED_EXTENSIONS | DOC_EXTENSIONS
        assert ".py" in ALL_SUPPORTED_EXTENSIONS  # code
        assert ".md" in ALL_SUPPORTED_EXTENSIONS  # doc

    def test_is_doc_file_true_for_docs(self):
        from core.kgraph.tree_sitter_parser import is_doc_file
        assert is_doc_file("README.md") is True
        assert is_doc_file("notes.txt") is True
        assert is_doc_file("docs/api.rst") is True

    def test_is_doc_file_false_for_code(self):
        from core.kgraph.tree_sitter_parser import is_doc_file
        assert is_doc_file("main.py") is False
        assert is_doc_file("app.js") is False
        assert is_doc_file("main.go") is False

    def test_is_doc_file_case_insensitive(self):
        from core.kgraph.tree_sitter_parser import is_doc_file
        assert is_doc_file("README.MD") is True
        assert is_doc_file("notes.TXT") is True


class TestExtractDocChunks:
    """v1.3: extract_doc_chunks() in embeddings.py."""

    def test_returns_proper_dict_shape(self):
        """Each chunk must have {name, type, source, line_start, line_end}."""
        from core.kgraph.embeddings import extract_doc_chunks
        # Mock chonkie to return 2 chunks
        with patch("tools.file_ops.actions.read_file._chunk_text", return_value=["chunk 1 text", "chunk 2 text"]):
            chunks = extract_doc_chunks("# README\nSome content.", "README.md", "t1")
        assert len(chunks) == 2
        for c in chunks:
            assert "name" in c
            assert "type" in c
            assert "source" in c
            assert "line_start" in c
            assert "line_end" in c
            assert c["type"] == "doc"

    def test_chunk_names_encode_position(self):
        """Names should be doc_chunk_N_of_M."""
        from core.kgraph.embeddings import extract_doc_chunks
        with patch("tools.file_ops.actions.read_file._chunk_text", return_value=["a", "b", "c"]):
            chunks = extract_doc_chunks("content", "test.md", "t1")
        assert chunks[0]["name"] == "doc_chunk_0_of_3"
        assert chunks[1]["name"] == "doc_chunk_1_of_3"
        assert chunks[2]["name"] == "doc_chunk_2_of_3"

    def test_fallback_single_chunk_when_chonkie_missing(self):
        """When chonkie is not installed, fall back to a single doc chunk."""
        from core.kgraph.embeddings import extract_doc_chunks
        with patch("tools.file_ops.actions.read_file._chunk_text", side_effect=RuntimeError("chonkie not installed")):
            chunks = extract_doc_chunks("# Title\nContent here.", "README.md", "t1")
        assert len(chunks) == 1
        assert chunks[0]["name"] == "doc_chunk_0_of_1"
        assert chunks[0]["type"] == "doc"
        assert "# Title" in chunks[0]["source"]

    def test_empty_content_returns_single_empty_chunk(self):
        """Empty content still returns a valid chunk list (not empty)."""
        from core.kgraph.embeddings import extract_doc_chunks
        chunks = extract_doc_chunks("", "empty.md", "t1")
        assert len(chunks) == 1
        assert chunks[0]["type"] == "doc"

    def test_line_start_line_end_are_nonzero_for_multiline_content(self):
        """[v1.4.1 P2-3] Doc chunks must carry non-zero line numbers.

        Was: 0/0 because chonkie chunks don't expose line numbers directly.
        Now: computed by scanning the original content for the chunk's first
        character. For a single-chunk file, line_start should be 1 and
        line_end should be the number of lines in the chunk.
        """
        from core.kgraph.embeddings import extract_doc_chunks
        multi_line_content = "line 1\nline 2\nline 3\nline 4"
        with patch("tools.file_ops.actions.read_file._chunk_text",
                   return_value=["line 3\nline 4"]):
            chunks = extract_doc_chunks(multi_line_content, "test.md", "t1")
        assert len(chunks) == 1
        # "line 3\nline 4" starts at line 3 (1-based) and ends at line 4.
        assert chunks[0]["line_start"] == 3
        assert chunks[0]["line_end"] == 4

    def test_line_start_is_one_for_first_chunk(self):
        """[v1.4.1 P2-3] The first chunk should start at line 1."""
        from core.kgraph.embeddings import extract_doc_chunks
        content = "first line\nsecond line\n"
        with patch("tools.file_ops.actions.read_file._chunk_text",
                   return_value=["first line\nsecond line\n"]):
            chunks = extract_doc_chunks(content, "test.md", "t1")
        assert len(chunks) == 1
        assert chunks[0]["line_start"] == 1

    def test_line_start_falls_back_to_zero_when_chunk_not_found(self):
        """[v1.4.1 P2-3] If the chunk text isn't in the content, line_start is 0.

        Defensive: chonkie may normalize whitespace, so the exact chunk text
        might not be findable. The fallback is 0/0 (old behavior).
        """
        from core.kgraph.embeddings import extract_doc_chunks
        content = "completely different content"
        # Return a chunk that doesn't appear verbatim in the content.
        with patch("tools.file_ops.actions.read_file._chunk_text",
                   return_value=["this chunk text is not in the content"]):
            chunks = extract_doc_chunks(content, "test.md", "t1")
        assert len(chunks) == 1
        # The chunk text isn't found, and neither is its first line —
        # line_start should fall back to 0.
        assert chunks[0]["line_start"] == 0


class TestParseAndStoreDocBranch:
    """v1.3: parse_and_store correctly branches doc vs code files."""

    def test_doc_file_gets_no_graph_edges(self, mocker, tmp_path):
        """Doc files should be stored as nodes with empty target_paths."""
        from workflows.understand_impl.nodes.parse_and_store import node_parse_and_store
        from core.kgraph.project import ProjectManager as _RealPM

        # Create a real temp file so Path(full_path).read_text() works
        doc_file = tmp_path / "README.md"
        doc_file.write_text("# Test\nDoc content here.")

        # Mock the external dependencies, not the internal logic.
        # [v1.4.1] Must set MAX_FILE_SIZE_BYTES on the mock CLASS (not just the
        # instance) because parse_and_store accesses it as
        # `ProjectManager.MAX_FILE_SIZE_BYTES`.
        mock_store = MagicMock()
        mocker.patch("workflows.understand_impl.nodes.parse_and_store.GraphStore", return_value=mock_store)
        mock_pm_class = mocker.patch("workflows.understand_impl.nodes.parse_and_store.ProjectManager")
        mock_pm_class.MAX_FILE_SIZE_BYTES = _RealPM.MAX_FILE_SIZE_BYTES
        mock_pm_class.return_value.project_id = "test"
        mock_pm_class.return_value.artifact_root = tmp_path / ".understand"
        mock_pm_class.return_value.is_agent_root = False
        mocker.patch("workflows.understand_impl.nodes.parse_and_store.upsert_file_vectors", return_value=0)
        mocker.patch("workflows.understand_impl.nodes.parse_and_store.extract_doc_chunks",
                      return_value=[{"name": "d0", "type": "doc", "source": "x", "line_start": 0, "line_end": 0}])

        state = {
            "project_path": str(tmp_path),
            "project_id": "test",
            "artifact_dir": str(tmp_path / ".understand"),
            "is_agent_root": False,
            "trace_id": "t1",
            "status": "running",
            "files_to_parse": [(str(doc_file), "README.md", "hash123", 1.0, 100)],
            "skip_embeddings": True,
        }

        node_parse_and_store(state)

        # upsert_file_graph should have been called with empty target_paths
        mock_store.upsert_file_graph.assert_called_once()
        call_args = mock_store.upsert_file_graph.call_args
        # args: (project_id, rel_path, hash, target_paths, mtime, size)
        assert call_args[0][3] == []  # 4th positional arg = target_paths list

    def test_code_file_still_gets_graph_edges(self, mocker, tmp_path):
        """Code files should still get tree-sitter import edges (not broken by v1.3)."""
        from workflows.understand_impl.nodes.parse_and_store import node_parse_and_store
        from core.kgraph.project import ProjectManager as _RealPM

        # Create a real temp file so Path(full_path).read_text() works
        code_file = tmp_path / "main.py"
        code_file.write_text("import os\nimport sys\n")

        mock_store = MagicMock()
        mocker.patch("workflows.understand_impl.nodes.parse_and_store.GraphStore", return_value=mock_store)
        # [v1.4.1] Set MAX_FILE_SIZE_BYTES on the mock CLASS.
        mock_pm_class = mocker.patch("workflows.understand_impl.nodes.parse_and_store.ProjectManager")
        mock_pm_class.MAX_FILE_SIZE_BYTES = _RealPM.MAX_FILE_SIZE_BYTES
        mock_pm_class.return_value.project_id = "test"
        mock_pm_class.return_value.artifact_root = tmp_path / ".understand"
        mock_pm_class.return_value.is_agent_root = False
        mocker.patch("workflows.understand_impl.nodes.parse_and_store.upsert_file_vectors", return_value=0)
        mocker.patch("workflows.understand_impl.nodes.parse_and_store.extract_definitions", return_value=[])
        mocker.patch("workflows.understand_impl.nodes.parse_and_store.extract_imports", return_value=["os", "sys"])

        state = {
            "project_path": str(tmp_path),
            "project_id": "test",
            "artifact_dir": str(tmp_path / ".understand"),
            "is_agent_root": False,
            "trace_id": "t1",
            "status": "running",
            "files_to_parse": [(str(code_file), "main.py", "hash123", 1.0, 100)],
            "skip_embeddings": True,
        }

        node_parse_and_store(state)

        # upsert_file_graph should have been called with non-empty target_paths
        mock_store.upsert_file_graph.assert_called_once()
        call_args = mock_store.upsert_file_graph.call_args
        target_paths = call_args[0][3]
        assert len(target_paths) > 0  # has edges
        assert "os" in target_paths
