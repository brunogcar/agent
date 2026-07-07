"""tests/workflows/understand/test_embeddings.py
Tests for code embedding: extract_definitions (AST chunking) + embed_texts
(LM Studio endpoint) + upsert_file_vectors (ChromaDB integration).

All tests mock the LM Studio HTTP endpoint — no real LM Studio required.
"""
from __future__ import annotations

import pytest
from unittest.mock import patch, MagicMock


# ─── extract_definitions (AST chunking) ─────────────────────────────────────

class TestExtractDefinitions:
    def test_extracts_function(self):
        from core.kgraph.embeddings import extract_definitions
        code = "def foo():\n    return 42\n"
        defs = extract_definitions(code)
        assert len(defs) == 1
        assert defs[0]["name"] == "foo"
        assert defs[0]["type"] == "function"
        assert defs[0]["line_start"] == 1

    def test_extracts_class(self):
        from core.kgraph.embeddings import extract_definitions
        code = "class Bar:\n    pass\n"
        defs = extract_definitions(code)
        assert len(defs) == 1
        assert defs[0]["name"] == "Bar"
        assert defs[0]["type"] == "class"

    def test_extracts_module_docstring(self):
        """[v1.1] Module docstrings were extracted by the old AST parser.
        [#4] tree-sitter doesn't extract docstrings as separate definitions —
        they're part of the module node. The function is still extracted."""
        from core.kgraph.embeddings import extract_definitions
        code = '"""Module doc."""\n\ndef foo():\n    pass\n'
        defs = extract_definitions(code)
        # tree-sitter extracts the function but not the docstring as a separate chunk
        assert len(defs) >= 1
        names = [d["name"] for d in defs]
        assert "foo" in names

    def test_extracts_multiple_definitions(self):
        from core.kgraph.embeddings import extract_definitions
        code = (
            "def foo():\n    pass\n\n"
            "def bar():\n    pass\n\n"
            "class Baz:\n    pass\n"
        )
        defs = extract_definitions(code)
        assert len(defs) == 3
        names = [d["name"] for d in defs]
        assert "foo" in names
        assert "bar" in names
        assert "Baz" in names

    def test_async_function(self):
        from core.kgraph.embeddings import extract_definitions
        code = "async def fetch():\n    return 1\n"
        defs = extract_definitions(code)
        assert len(defs) == 1
        assert defs[0]["name"] == "fetch"
        assert defs[0]["type"] == "function"

    def test_no_definitions_falls_back_to_module_chunk(self):
        """Files with no top-level defs (scripts, __init__.py) get a single module chunk."""
        from core.kgraph.embeddings import extract_definitions
        code = "x = 1\ny = 2\nprint(x + y)\n"
        defs = extract_definitions(code)
        assert len(defs) == 1
        assert defs[0]["name"] == "<module>"
        assert defs[0]["type"] == "module"

    def test_syntax_error_falls_back_to_module_chunk(self):
        """[#4] tree-sitter has error recovery — it may still extract partial
        definitions from broken syntax. The key requirement: it must not crash
        and must return a list of dicts."""
        from core.kgraph.embeddings import extract_definitions
        code = "def broken(:\n    pass\n"
        defs = extract_definitions(code)
        # tree-sitter may extract the partial function or fall back to <module>
        assert isinstance(defs, list)
        assert len(defs) >= 1
        assert "source" in defs[0]
        assert "name" in defs[0]

    def test_line_ranges_correct(self):
        from core.kgraph.embeddings import extract_definitions
        code = "\n\ndef foo():\n    return 42\n\nclass Bar:\n    pass\n"
        defs = extract_definitions(code)
        func_def = [d for d in defs if d["name"] == "foo"][0]
        assert func_def["line_start"] == 3
        assert func_def["line_end"] == 4

    def test_source_code_extracted(self):
        from core.kgraph.embeddings import extract_definitions
        code = "def foo():\n    return 42\n"
        defs = extract_definitions(code)
        assert "return 42" in defs[0]["source"]


# ─── embed_texts (LM Studio endpoint) ───────────────────────────────────────

class TestEmbedTexts:
    def test_returns_vectors_on_success(self, mocker):
        """embed_texts must return a list of vectors when LM Studio responds."""
        from core.kgraph.embeddings import embed_texts
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "data": [
                {"embedding": [0.1, 0.2, 0.3]},
                {"embedding": [0.4, 0.5, 0.6]},
            ]
        }
        mock_resp.raise_for_status = MagicMock()
        mocker.patch("httpx.post", return_value=mock_resp)

        result = embed_texts(["hello", "world"])
        assert result is not None
        assert len(result) == 2
        assert result[0] == [0.1, 0.2, 0.3]

    def test_returns_none_on_connection_failure(self, mocker):
        """If LM Studio is not running, return None (graceful degradation)."""
        from core.kgraph.embeddings import embed_texts
        mocker.patch("httpx.post", side_effect=Exception("Connection refused"))
        result = embed_texts(["hello"])
        assert result is None

    def test_returns_none_when_disabled(self, mocker):
        """When EMBEDDING_ENABLED=false, return None without calling the endpoint."""
        from core.kgraph.embeddings import embed_texts
        mock_post = mocker.patch("httpx.post")
        with patch("core.kgraph.embeddings.cfg") as mock_cfg:
            mock_cfg.embedding_enabled = False
            result = embed_texts(["hello"])
        assert result is None
        assert not mock_post.called

    def test_empty_list_returns_empty(self):
        from core.kgraph.embeddings import embed_texts
        assert embed_texts([]) == []

    def test_calls_correct_endpoint(self, mocker):
        """Must POST to {base_url}/embeddings with model + input."""
        from core.kgraph.embeddings import embed_texts
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"data": [{"embedding": [0.1]}]}
        mock_resp.raise_for_status = MagicMock()
        mock_post = mocker.patch("httpx.post", return_value=mock_resp)

        embed_texts(["test text"], trace_id="t1")

        call_args = mock_post.call_args
        url = call_args[0][0] if call_args[0] else call_args[1]["url"]
        assert "/embeddings" in url
        json_payload = call_args[1]["json"]
        assert "model" in json_payload
        assert json_payload["input"] == ["test text"]


# ─── upsert_file_vectors (ChromaDB integration) ─────────────────────────────

class TestUpsertFileVectors:
    def test_deletes_old_vectors_before_inserting(self, mocker):
        """Must delete old vectors for the file before adding new ones."""
        from core.kgraph.vectors import upsert_file_vectors
        mock_collection = MagicMock()
        mocker.patch(
            "core.kgraph.vectors.get_project_vector_collection",
            return_value=mock_collection,
        )
        mocker.patch(
            "core.kgraph.embeddings.embed_texts",
            return_value=[[0.1, 0.2]],
        )
        definitions = [{"name": "foo", "type": "function", "source": "def foo(): pass",
                        "line_start": 1, "line_end": 1}]
        upsert_file_vectors("proj1", "core/x.py", definitions, trace_id="t1")
        mock_collection.delete.assert_called_once_with(where={"file_path": "core/x.py"})

    def test_upserts_new_vectors(self, mocker):
        from core.kgraph.vectors import upsert_file_vectors
        mock_collection = MagicMock()
        mocker.patch("core.kgraph.vectors.get_project_vector_collection", return_value=mock_collection)
        mocker.patch("core.kgraph.embeddings.embed_texts", return_value=[[0.1, 0.2], [0.3, 0.4]])
        definitions = [
            {"name": "foo", "type": "function", "source": "def foo(): pass", "line_start": 1, "line_end": 1},
            {"name": "Bar", "type": "class", "source": "class Bar: pass", "line_start": 3, "line_end": 3},
        ]
        count = upsert_file_vectors("proj1", "core/x.py", definitions, trace_id="t1")
        assert count == 2
        mock_collection.upsert.assert_called_once()
        call_kwargs = mock_collection.upsert.call_args[1]
        assert len(call_kwargs["ids"]) == 2
        assert len(call_kwargs["embeddings"]) == 2

    def test_returns_zero_when_embedding_fails(self, mocker):
        """When embed_texts returns None (LM Studio down), return 0 gracefully."""
        from core.kgraph.vectors import upsert_file_vectors
        mock_collection = MagicMock()
        mocker.patch("core.kgraph.vectors.get_project_vector_collection", return_value=mock_collection)
        mocker.patch("core.kgraph.embeddings.embed_texts", return_value=None)
        definitions = [{"name": "foo", "type": "function", "source": "code",
                        "line_start": 1, "line_end": 1}]
        count = upsert_file_vectors("proj1", "core/x.py", definitions, trace_id="t1")
        assert count == 0
        mock_collection.upsert.assert_not_called()

    def test_empty_definitions_returns_zero(self, mocker):
        from core.kgraph.vectors import upsert_file_vectors
        mock_collection = MagicMock()
        mocker.patch("core.kgraph.vectors.get_project_vector_collection", return_value=mock_collection)
        count = upsert_file_vectors("proj1", "core/x.py", [], trace_id="t1")
        assert count == 0
        mock_collection.upsert.assert_not_called()

    def test_metadata_includes_file_and_line_info(self, mocker):
        from core.kgraph.vectors import upsert_file_vectors
        mock_collection = MagicMock()
        mocker.patch("core.kgraph.vectors.get_project_vector_collection", return_value=mock_collection)
        mocker.patch("core.kgraph.embeddings.embed_texts", return_value=[[0.1, 0.2]])
        definitions = [{"name": "foo", "type": "function", "source": "def foo(): pass",
                        "line_start": 10, "line_end": 20}]
        upsert_file_vectors("proj1", "core/x.py", definitions, trace_id="t1")
        call_kwargs = mock_collection.upsert.call_args[1]
        meta = call_kwargs["metadatas"][0]
        assert meta["file_path"] == "core/x.py"
        assert meta["name"] == "foo"
        assert meta["type"] == "function"
        assert meta["line_start"] == 10
        assert meta["line_end"] == 20


# ─── query_similar_code (semantic search) ───────────────────────────────────

class TestQuerySimilarCode:
    def test_returns_results_on_success(self, mocker):
        from core.kgraph.vectors import query_similar_code
        mock_collection = MagicMock()
        mock_collection.query.return_value = {
            "metadatas": [[{"file_path": "a.py", "name": "foo", "type": "function",
                            "line_start": 1, "line_end": 5}]],
            "documents": [["def foo(): pass"]],
            "distances": [[0.1]],
        }
        mocker.patch("core.kgraph.vectors.get_project_vector_collection", return_value=mock_collection)
        mocker.patch("core.kgraph.embeddings.embed_texts", return_value=[[0.1, 0.2]])
        results = query_similar_code("proj1", "how does foo work?", trace_id="t1")
        assert len(results) == 1
        assert results[0]["file_path"] == "a.py"
        assert results[0]["name"] == "foo"

    def test_returns_empty_when_embedding_fails(self, mocker):
        from core.kgraph.vectors import query_similar_code
        mocker.patch("core.kgraph.embeddings.embed_texts", return_value=None)
        results = query_similar_code("proj1", "query", trace_id="t1")
        assert results == []
