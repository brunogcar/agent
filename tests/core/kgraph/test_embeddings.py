"""tests/workflows/understand/test_embeddings.py
Tests for code embedding: extract_definitions (AST chunking) + embed_texts
(LM Studio endpoint) + upsert_file_vectors (ChromaDB integration).

All tests mock the LM Studio HTTP endpoint — no real LM Studio required.

[v1.4.1 P1-3] upsert_file_vectors + get_project_vector_collection +
query_similar_code now take a `pm: ProjectManager` instead of `project_id: str`.
Tests pass a MagicMock with the required attributes.

[v1.7] Additional tests:
  - Embedding cache (md5-keyed, 10000-entry cap, clear_embedding_cache()).
  - Per-project embedding model (pm.get_embedding_model() + embed_texts model=).
"""
from __future__ import annotations

import pytest
from unittest.mock import patch, MagicMock


def _fake_pm(project_id: str = "proj1", is_agent_root: bool = False, artifact_root=None):
    """[v1.4.1 P1-3] Build a fake ProjectManager for vector tests.

    Avoids the cost of instantiating a real PM (which walks the source tree
    for stats) and lets us test the project-scoped path computation directly.
    """
    from pathlib import Path
    pm = MagicMock()
    pm.project_id = project_id
    pm.is_agent_root = is_agent_root
    pm.artifact_root = Path(artifact_root) if artifact_root else Path("/tmp/fake_project/.understand")
    return pm


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
    """[v1.7] All embed_texts tests must clear the module-level cache first,
    otherwise a cached text from a previous test would short-circuit the HTTP
    call and the test would silently pass without exercising the path under
    test (or, worse, return a cached vector when the test expects None).
    """

    def test_returns_vectors_on_success(self, mocker):
        """embed_texts must return a list of vectors when LM Studio responds."""
        from core.kgraph.embeddings import embed_texts, reset_embedding_check, clear_embedding_cache
        # [v1.7] Clear cache so we actually hit HTTP.
        clear_embedding_cache()
        # [v1.4.1] Reset the cached availability flag so our mocked httpx.post
        # is actually reached (is_embedding_available() caches False when LM
        # Studio is unreachable, which short-circuits embed_texts before the
        # httpx.post call).
        reset_embedding_check()
        mocker.patch("core.kgraph.embeddings.is_embedding_available", return_value=True)

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
        from core.kgraph.embeddings import embed_texts, reset_embedding_check, clear_embedding_cache
        # [v1.7] Clear cache so we actually hit HTTP (and then fail).
        clear_embedding_cache()
        # [v1.4.1] Reset + force availability True so the httpx.post call is
        # actually reached (and then fails via the side_effect below).
        reset_embedding_check()
        mocker.patch("core.kgraph.embeddings.is_embedding_available", return_value=True)
        mocker.patch("httpx.post", side_effect=Exception("Connection refused"))
        result = embed_texts(["hello"])
        assert result is None

    def test_returns_none_when_disabled(self, mocker):
        """When EMBEDDING_ENABLED=false, return None without calling the endpoint."""
        from core.kgraph.embeddings import embed_texts, clear_embedding_cache
        # [v1.7] Clear cache — though it doesn't matter here since disabled
        # check fires before the cache lookup.
        clear_embedding_cache()
        mock_post = mocker.patch("httpx.post")
        with patch("core.kgraph.embeddings.cfg") as mock_cfg:
            mock_cfg.embedding_enabled = False
            mock_cfg.embedding_model = "all-MiniLM-L6-v2-GGUF"
            mock_cfg.embedding_base_url = "http://localhost:1234/v1"
            result = embed_texts(["hello"])
        assert result is None
        assert not mock_post.called

    def test_empty_list_returns_empty(self):
        from core.kgraph.embeddings import embed_texts, clear_embedding_cache
        # [v1.7] Clear cache for hygiene.
        clear_embedding_cache()
        assert embed_texts([]) == []

    def test_calls_correct_endpoint(self, mocker):
        """Must POST to {base_url}/embeddings with model + input."""
        from core.kgraph.embeddings import embed_texts, reset_embedding_check, clear_embedding_cache
        # [v1.7] Clear cache so httpx.post IS called (cache hit would skip it).
        clear_embedding_cache()
        # [v1.4.1] Reset + force availability True so the httpx.post call happens.
        reset_embedding_check()
        mocker.patch("core.kgraph.embeddings.is_embedding_available", return_value=True)

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
        upsert_file_vectors(_fake_pm(), "core/x.py", definitions, trace_id="t1")
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
        count = upsert_file_vectors(_fake_pm(), "core/x.py", definitions, trace_id="t1")
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
        count = upsert_file_vectors(_fake_pm(), "core/x.py", definitions, trace_id="t1")
        assert count == 0
        mock_collection.upsert.assert_not_called()

    def test_empty_definitions_returns_zero(self, mocker):
        from core.kgraph.vectors import upsert_file_vectors
        mock_collection = MagicMock()
        mocker.patch("core.kgraph.vectors.get_project_vector_collection", return_value=mock_collection)
        count = upsert_file_vectors(_fake_pm(), "core/x.py", [], trace_id="t1")
        assert count == 0
        mock_collection.upsert.assert_not_called()

    def test_metadata_includes_file_and_line_info(self, mocker):
        from core.kgraph.vectors import upsert_file_vectors
        mock_collection = MagicMock()
        mocker.patch("core.kgraph.vectors.get_project_vector_collection", return_value=mock_collection)
        mocker.patch("core.kgraph.embeddings.embed_texts", return_value=[[0.1, 0.2]])
        definitions = [{"name": "foo", "type": "function", "source": "def foo(): pass",
                        "line_start": 10, "line_end": 20}]
        upsert_file_vectors(_fake_pm(), "core/x.py", definitions, trace_id="t1")
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
        results = query_similar_code(_fake_pm(), "how does foo work?", trace_id="t1")
        assert len(results) == 1
        assert results[0]["file_path"] == "a.py"
        assert results[0]["name"] == "foo"

    def test_returns_empty_when_embedding_fails(self, mocker):
        from core.kgraph.vectors import query_similar_code
        mocker.patch("core.kgraph.embeddings.embed_texts", return_value=None)
        results = query_similar_code(_fake_pm(), "query", trace_id="t1")
        assert results == []


# ─── get_project_vector_collection path computation ────────────────────────

class TestProjectScopedVectorPath:
    """[v1.4.1 P1-3] ChromaDB path must be project-scoped.

    Was: hardcoded `cfg.agent_root / ".understand" / "chroma"` — used the
    AGENT root for ALL projects. Now computed from `pm`:
      - Agent root → cfg.memory_root / "understand" / "chroma"
      - Workspace project → pm.artifact_root / "chroma"
    """

    def test_workspace_project_path(self, mocker, tmp_path):
        """Workspace project vectors live under {project}/.understand/chroma/."""
        import core.kgraph.vectors as vectors_mod
        from core.kgraph.vectors import get_project_vector_collection

        artifact_root = tmp_path / "myproj" / ".understand"
        pm = _fake_pm(project_id="abc123", is_agent_root=False, artifact_root=str(artifact_root))

        captured_path = {}
        def fake_persistent_client(path):
            captured_path["path"] = path
            client = MagicMock()
            client.get_or_create_collection.return_value = MagicMock()
            return client
        mocker.patch("chromadb.PersistentClient", side_effect=fake_persistent_client)
        # Clear the client cache so our mock is used.
        vectors_mod._chroma_clients.clear()

        get_project_vector_collection(pm)

        assert "path" in captured_path
        assert captured_path["path"] == str(artifact_root / "chroma")

    def test_agent_root_path(self, mocker, tmp_path):
        """Agent root vectors live under cfg.memory_root/understand/chroma/."""
        import core.kgraph.vectors as vectors_mod
        from core.kgraph.vectors import get_project_vector_collection
        from core.config import cfg

        pm = _fake_pm(project_id="agentroot", is_agent_root=True)

        captured_path = {}
        def fake_persistent_client(path):
            captured_path["path"] = path
            client = MagicMock()
            client.get_or_create_collection.return_value = MagicMock()
            return client
        mocker.patch("chromadb.PersistentClient", side_effect=fake_persistent_client)
        vectors_mod._chroma_clients.clear()

        get_project_vector_collection(pm)

        assert "path" in captured_path
        expected = str(cfg.memory_root / "understand" / "chroma")
        assert captured_path["path"] == expected


# ─── [v1.4.2] extract_doc_chunks line numbers ───────────────────────────────
# (The `test_chromadb_path_project_scoped` test from the v1.4.2 task description
# is already covered by TestProjectScopedVectorPath above — added in Phase 1.)

class TestDocChunkLineNumbers:
    """[v1.4.2] extract_doc_chunks computes non-zero line_start/line_end.

    Tests the kgraph-level extract_doc_chunks directly (the understand-side
    test_doc_indexing.py has equivalent coverage at the node-integration
    level — these tests are here because extract_doc_chunks lives in
    core.kgraph.embeddings, which is the right home for kgraph-module tests
    after the v1.4.2 test refactor).
    """

    def test_doc_chunk_line_numbers(self):
        """Multi-line .md content → chunks carry non-zero line numbers.

        Was: 0/0 because chonkie chunks don't expose line numbers directly
        (v1.4.1 P2-3 fix). Now: line_start is computed by scanning the
        original content for the chunk's first character.
        """
        from core.kgraph.embeddings import extract_doc_chunks
        multi_line_content = "line 1\nline 2\nline 3\nline 4"
        # Patch chonkie to return a chunk starting at line 3.
        with patch("tools.file_ops.actions.read_file._chunk_text",
                   return_value=["line 3\nline 4"]):
            chunks = extract_doc_chunks(multi_line_content, "test.md", "t1")
        assert len(chunks) == 1
        # "line 3\nline 4" starts at line 3 (1-based) and ends at line 4.
        assert chunks[0]["line_start"] == 3, (
            f"expected line_start=3, got {chunks[0]['line_start']}"
        )
        assert chunks[0]["line_end"] == 4, (
            f"expected line_end=4, got {chunks[0]['line_end']}"
        )

    def test_first_chunk_starts_at_line_1(self):
        """[v1.4.1 P2-3] A chunk matching the start of content has line_start=1."""
        from core.kgraph.embeddings import extract_doc_chunks
        # Note: NO trailing newline — chunk_text.count("\n") = 1, so line_end = 1 + 1 = 2.
        content = "first line\nsecond line"
        with patch("tools.file_ops.actions.read_file._chunk_text",
                   return_value=["first line\nsecond line"]):
            chunks = extract_doc_chunks(content, "test.md", "t1")
        assert len(chunks) == 1
        assert chunks[0]["line_start"] == 1
        assert chunks[0]["line_end"] == 2  # line_start (1) + 1 newline in chunk = 2

    def test_chunk_not_in_content_falls_back_to_zero(self):
        """[v1.4.1 P2-3] Defensive — chunk text not found → line_start=0."""
        from core.kgraph.embeddings import extract_doc_chunks
        content = "completely different content"
        with patch("tools.file_ops.actions.read_file._chunk_text",
                   return_value=["this chunk text is not in the content"]):
            chunks = extract_doc_chunks(content, "test.md", "t1")
        assert len(chunks) == 1
        assert chunks[0]["line_start"] == 0


# ─── [v1.7] Embedding cache ──────────────────────────────────────────────────

class TestEmbeddingCache:
    """[v1.7] embed_texts() caches by md5(text). Cache hits skip the HTTP call.

    The cache is module-level + keyed by md5(text). It persists across calls
    in the same process. clear_embedding_cache() empties it (for testing).

    Tests cover: cache hit (no HTTP), cache miss (HTTP called), partial hit
    (only uncached texts hit HTTP), clear_embedding_cache (cache cleared,
    next embed hits HTTP again).
    """

    def test_embedding_cache_hit(self, mocker):
        """Embed a text, embed again — verify HTTP is called only ONCE."""
        from core.kgraph.embeddings import (
            embed_texts, reset_embedding_check, clear_embedding_cache,
        )
        clear_embedding_cache()
        reset_embedding_check()
        mocker.patch("core.kgraph.embeddings.is_embedding_available", return_value=True)

        mock_resp = MagicMock()
        mock_resp.json.return_value = {"data": [{"embedding": [0.1, 0.2]}]}
        mock_resp.raise_for_status = MagicMock()
        mock_post = mocker.patch("httpx.post", return_value=mock_resp)

        # First call — cache miss, HTTP called.
        r1 = embed_texts(["alpha"])
        assert r1 == [[0.1, 0.2]]
        assert mock_post.call_count == 1

        # Second call — cache hit, HTTP NOT called.
        r2 = embed_texts(["alpha"])
        assert r2 == [[0.1, 0.2]]
        assert mock_post.call_count == 1, (
            f"HTTP should not be called on cache hit; got {mock_post.call_count} calls"
        )

    def test_embedding_cache_miss(self, mocker):
        """Embed a new text → HTTP is called (cache miss)."""
        from core.kgraph.embeddings import (
            embed_texts, reset_embedding_check, clear_embedding_cache,
        )
        clear_embedding_cache()
        reset_embedding_check()
        mocker.patch("core.kgraph.embeddings.is_embedding_available", return_value=True)

        mock_resp = MagicMock()
        mock_resp.json.return_value = {"data": [{"embedding": [0.5]}]}
        mock_resp.raise_for_status = MagicMock()
        mock_post = mocker.patch("httpx.post", return_value=mock_resp)

        result = embed_texts(["brand-new-text"])
        assert result == [[0.5]]
        assert mock_post.call_count == 1, (
            f"HTTP should be called once on cache miss; got {mock_post.call_count}"
        )

    def test_embedding_cache_partial_hit(self, mocker):
        """Embed [A, B], then embed [A, C] — only C hits HTTP."""
        from core.kgraph.embeddings import (
            embed_texts, reset_embedding_check, clear_embedding_cache,
        )
        clear_embedding_cache()
        reset_embedding_check()
        mocker.patch("core.kgraph.embeddings.is_embedding_available", return_value=True)

        # Mock returns one embedding per input (the count must match).
        def fake_post(url, json=None, **kwargs):
            resp = MagicMock()
            resp.json.return_value = {
                "data": [{"embedding": [0.1 * i]} for i in range(len(json["input"]))]
            }
            resp.raise_for_status = MagicMock()
            return resp

        mock_post = mocker.patch("httpx.post", side_effect=fake_post)

        # First call — both A and B miss cache. HTTP called once with [A, B].
        r1 = embed_texts(["A-text", "B-text"])
        assert len(r1) == 2
        assert mock_post.call_count == 1
        # Verify the first HTTP call was for both texts.
        first_payload = mock_post.call_args[1]["json"]["input"]
        assert first_payload == ["A-text", "B-text"]

        # Second call — A is cached, only C is uncached.
        # HTTP should be called once with just [C-text] (the uncached one).
        r2 = embed_texts(["A-text", "C-text"])
        assert len(r2) == 2
        assert mock_post.call_count == 2, (
            f"HTTP should be called once more for the partial miss; got {mock_post.call_count}"
        )
        # The second call's payload should contain only the uncached text.
        second_payload = mock_post.call_args[1]["json"]["input"]
        assert second_payload == ["C-text"], (
            f"second HTTP call should embed only the uncached text; got: {second_payload}"
        )
        # A's vector should be the same as before (cache hit).
        assert r2[0] == r1[0]
        # C's vector should be present (newly embedded).
        assert r2[1] is not None

    def test_clear_embedding_cache(self, mocker):
        """Embed, clear cache, embed again — HTTP called twice."""
        from core.kgraph.embeddings import (
            embed_texts, reset_embedding_check, clear_embedding_cache,
        )
        clear_embedding_cache()
        reset_embedding_check()
        mocker.patch("core.kgraph.embeddings.is_embedding_available", return_value=True)

        mock_resp = MagicMock()
        mock_resp.json.return_value = {"data": [{"embedding": [0.7]}]}
        mock_resp.raise_for_status = MagicMock()
        mock_post = mocker.patch("httpx.post", return_value=mock_resp)

        # First call — cache miss.
        embed_texts(["clearable-text"])
        assert mock_post.call_count == 1

        # Clear cache.
        clear_embedding_cache()

        # Second call — cache miss again (cache was cleared).
        embed_texts(["clearable-text"])
        assert mock_post.call_count == 2, (
            f"HTTP should be called again after clear_embedding_cache; "
            f"got {mock_post.call_count}"
        )


# ─── [v1.7] Per-project embedding model ──────────────────────────────────────

class TestPerProjectEmbeddingModel:
    """[v1.7] pm.get_embedding_model() reads .understand/config.json override.

    embed_texts() accepts an optional `model` parameter. When non-empty, it
    overrides cfg.embedding_model. Callers (vectors.upsert_file_vectors,
    vectors.query_similar_code) pass pm.get_embedding_model() through.
    """

    def test_get_embedding_model_fallback(self, tmp_path):
        """No config.json → returns cfg.embedding_model (global default)."""
        from core.kgraph.project import ProjectManager
        from core.config import cfg

        pm = ProjectManager(tmp_path, is_agent_root=False)
        pm.ensure_initialized()
        # No config.json written — should fall back to cfg.embedding_model.
        result = pm.get_embedding_model()
        assert result == cfg.embedding_model, (
            f"without config.json, should fall back to cfg.embedding_model; got: {result}"
        )

    def test_get_embedding_model_override(self, tmp_path):
        """config.json with embedding_model key → returns the override."""
        import json
        from core.kgraph.project import ProjectManager

        pm = ProjectManager(tmp_path, is_agent_root=False)
        pm.ensure_initialized()
        # Write a project-specific config.json with a custom model.
        config_path = pm.artifact_root / "config.json"
        config_path.write_text(json.dumps({
            "embedding_model": "custom-model-q8-v1.7",
        }), encoding="utf-8")

        result = pm.get_embedding_model()
        assert result == "custom-model-q8-v1.7", (
            f"should read override from config.json; got: {result}"
        )

    def test_get_embedding_model_corrupt_config_falls_back(self, tmp_path):
        """Corrupt config.json (invalid JSON) → falls back to cfg default."""
        from core.kgraph.project import ProjectManager
        from core.config import cfg

        pm = ProjectManager(tmp_path, is_agent_root=False)
        pm.ensure_initialized()
        # Write corrupt JSON.
        (pm.artifact_root / "config.json").write_text(
            "this is not valid json {{{", encoding="utf-8"
        )
        result = pm.get_embedding_model()
        assert result == cfg.embedding_model, (
            f"corrupt config.json should fall back to global default; got: {result}"
        )

    def test_embed_texts_uses_model_parameter(self, mocker):
        """embed_texts(model=...) sends the passed model in the HTTP payload."""
        from core.kgraph.embeddings import (
            embed_texts, reset_embedding_check, clear_embedding_cache,
        )
        clear_embedding_cache()
        reset_embedding_check()
        mocker.patch("core.kgraph.embeddings.is_embedding_available", return_value=True)

        mock_resp = MagicMock()
        mock_resp.json.return_value = {"data": [{"embedding": [0.1]}]}
        mock_resp.raise_for_status = MagicMock()
        mock_post = mocker.patch("httpx.post", return_value=mock_resp)

        embed_texts(["some text"], model="custom-model-xyz")

        payload = mock_post.call_args[1]["json"]
        assert payload["model"] == "custom-model-xyz", (
            f"HTTP payload should use the passed model; got: {payload['model']}"
        )

    def test_embed_texts_model_empty_uses_cfg_default(self, mocker):
        """embed_texts(model='') — empty string falls back to cfg.embedding_model."""
        from core.kgraph.embeddings import (
            embed_texts, reset_embedding_check, clear_embedding_cache,
        )
        from core.config import cfg
        clear_embedding_cache()
        reset_embedding_check()
        mocker.patch("core.kgraph.embeddings.is_embedding_available", return_value=True)

        mock_resp = MagicMock()
        mock_resp.json.return_value = {"data": [{"embedding": [0.1]}]}
        mock_resp.raise_for_status = MagicMock()
        mock_post = mocker.patch("httpx.post", return_value=mock_resp)

        embed_texts(["some text"], model="")  # empty → cfg default

        payload = mock_post.call_args[1]["json"]
        assert payload["model"] == cfg.embedding_model, (
            f"empty model= should fall back to cfg.embedding_model; got: {payload['model']}"
        )
