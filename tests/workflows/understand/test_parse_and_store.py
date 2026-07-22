"""tests/workflows/understand/test_parse_and_store.py

[v1.4.1] Tests for node_parse_and_store:
  - P1-1: defensive status=="failed" bail (returns {}).
  - P1-5: failed embedding batches append to the errors list.
  - P1-6: cancellation check at start + mid-parse + mid-batch.
  - P1-7: GraphStore creation inside try; finally checks for None.
  - P2-8: embedding batch size read from cfg.understand_embed_batch_size.
  - P2-10: errors list capped at 100 entries.
  - P3-1: file size re-checked before read_text (file that grew is skipped).
"""
from __future__ import annotations

from unittest.mock import patch, MagicMock
from pathlib import Path

from core.kgraph.project import ProjectManager


def _state(project_path, files_to_parse, **overrides):
    """Build a minimal state for node_parse_and_store tests."""
    base = {
        "project_path": str(project_path),
        "is_agent_root": False,
        "project_id": "testpid",
        "artifact_dir": str(Path(project_path) / ".understand"),
        "trace_id": "t1",
        "status": "running",
        "files_to_parse": files_to_parse,
        "skip_embeddings": True,  # default: skip Phase 2 for unit tests
    }
    base.update(overrides)
    return base


class TestDefensiveBailOnFailedStatus:
    """[v1.4.1 P1-1] If status=="failed", the node must return {} immediately."""

    def test_returns_empty_dict_when_status_failed(self, tmp_path):
        from workflows.understand_impl.nodes.parse_and_store import node_parse_and_store

        state = _state(tmp_path, [], status="failed")
        result = node_parse_and_store(state)
        assert result == {}


class TestCancellationCheck:
    """[v1.4.1 P1-6] Node must check is_workflow_cancelled at start."""

    def test_returns_failed_when_cancelled_at_start(self, mocker, tmp_path):
        from workflows.understand_impl.nodes.parse_and_store import node_parse_and_store

        mocker.patch("workflows.base.is_workflow_cancelled", return_value=True)
        # Even with files to parse, the cancel check at start should bail.
        state = _state(tmp_path, [("/x.py", "x.py", "h", 0.0, 10)])
        result = node_parse_and_store(state)
        assert result["status"] == "failed"
        assert "cancelled" in result["errors"][0].lower()


class TestGraphStoreInTry:
    """[v1.4.1 P1-7] GraphStore constructor failure must not crash with NameError."""

    def test_no_name_error_when_graphstore_constructor_raises(self, mocker, tmp_path):
        from workflows.understand_impl.nodes.parse_and_store import node_parse_and_store

        mocker.patch(
            "workflows.understand_impl.nodes.parse_and_store.GraphStore",
            side_effect=RuntimeError("simulated sqlite3 failure"),
        )
        state = _state(tmp_path, [("/x.py", "x.py", "h", 0.0, 10)])
        try:
            node_parse_and_store(state)
            raised = None
        except Exception as e:
            raised = e
        assert raised is not None
        assert not isinstance(raised, NameError), (
            "P1-7: GraphStore constructor failure must not raise NameError from finally"
        )


class TestEmbeddingBatchErrors:
    """[v1.4.1 P1-5] Failed embedding batches must append to the errors list."""

    def test_failed_batch_appends_error(self, mocker, tmp_path):
        """When embed_texts returns None for a batch, an error must be appended."""
        from workflows.understand_impl.nodes.parse_and_store import (
            node_parse_and_store,
        )
        
        code_file = tmp_path / "main.py"
        code_file.write_text("def foo():\n    pass\n")

        mock_store = MagicMock()
        mocker.patch(
            "workflows.understand_impl.nodes.parse_and_store.GraphStore",
            return_value=mock_store,
        )
        # [v1.4.1] Mock ProjectManager CLASS with MAX_FILE_SIZE_BYTES set
        # at the class level (parse_and_store accesses it as
        # `ProjectManager.MAX_FILE_SIZE_BYTES`, not `pm.MAX_FILE_SIZE_BYTES`).
        mock_pm_class = mocker.patch(
            "workflows.understand_impl.nodes.parse_and_store.ProjectManager",
        )
        mock_pm_class.MAX_FILE_SIZE_BYTES = ProjectManager.MAX_FILE_SIZE_BYTES
        mock_pm_class.return_value.project_id = "test"
        mock_pm_class.return_value.artifact_root = tmp_path / ".understand"
        mock_pm_class.return_value.is_agent_root = False
        # extract_definitions returns one definition so Phase 2 has work to do.
        mocker.patch(
            "workflows.understand_impl.nodes.parse_and_store.extract_definitions",
            return_value=[{"name": "foo", "type": "function", "source": "def foo(): pass",
                          "line_start": 1, "line_end": 2}],
        )
        # extract_imports returns empty (no edges).
        mocker.patch(
            "workflows.understand_impl.nodes.parse_and_store.extract_imports",
            return_value=frozenset(),
        )
        # is_embedding_available returns True so Phase 2 runs.
        mocker.patch(
            "core.kgraph.embeddings.is_embedding_available",
            return_value=True,
        )
        # embed_texts returns None → batch fails.
        mocker.patch(
            "core.kgraph.embeddings.embed_texts",
            return_value=None,
        )
        # get_project_vector_collection returns a mock collection.
        mock_collection = MagicMock()
        mocker.patch(
            "core.kgraph.vectors.get_project_vector_collection",
            return_value=mock_collection,
        )

        state = _state(tmp_path, [(str(code_file), "main.py", "h123", 1.0, 100)],
                       skip_embeddings=False)
        result = node_parse_and_store(state)

        # The errors list must contain a message about the failed batch.
        assert "errors" in result
        assert len(result["errors"]) > 0
        assert any("batch" in e.lower() or "embedding" in e.lower() for e in result["errors"]), (
            f"errors list must contain a batch-failure message, got: {result['errors']}"
        )


class TestErrorsCappedAt100:
    """[v1.4.1 P2-10] Errors list must be capped at 100 entries."""

    def test_errors_list_does_not_exceed_cap_plus_one(self, mocker, tmp_path):
        """When more than 100 files fail, the errors list is capped at 100 + summary."""
        from workflows.understand_impl.nodes.parse_and_store import (
            node_parse_and_store, _ERRORS_CAP,
        )
        
        # Create 200 fake file entries — all will fail to parse because
        # we mock read_text to raise.
        files = [(str(tmp_path / f"f{i}.py"), f"f{i}.py", "h", 0.0, 10) for i in range(200)]

        mock_store = MagicMock()
        mocker.patch(
            "workflows.understand_impl.nodes.parse_and_store.GraphStore",
            return_value=mock_store,
        )
        # [v1.4.1] Mock PM CLASS with MAX_FILE_SIZE_BYTES at class level.
        mock_pm_class = mocker.patch(
            "workflows.understand_impl.nodes.parse_and_store.ProjectManager",
        )
        mock_pm_class.MAX_FILE_SIZE_BYTES = ProjectManager.MAX_FILE_SIZE_BYTES
        mock_pm_class.return_value.project_id = "test"
        mock_pm_class.return_value.artifact_root = tmp_path / ".understand"
        mock_pm_class.return_value.is_agent_root = False

        # Make every file's stat succeed (small file) but read_text raise.
        # We patch Path.read_text to raise — the stat check passes, then read_text fails.
        def raising_read_text(self, *args, **kwargs):
            raise IOError("simulated read failure")

        mocker.patch("pathlib.Path.read_text", raising_read_text)

        state = _state(tmp_path, files, skip_embeddings=True)
        result = node_parse_and_store(state)

        # The errors list should be capped at _ERRORS_CAP (100) + 1 summary entry.
        assert len(result["errors"]) <= _ERRORS_CAP + 1
        # The last entry should be the "... and N more" summary.
        if len(result["errors"]) > _ERRORS_CAP:
            last = result["errors"][-1]
            assert "more errors" in last.lower() or "capped" in last.lower(), (
                f"cap-summary entry missing or malformed: {last}"
            )


class TestFileSizeRecheck:
    """[v1.4.1 P3-1] File size must be re-checked before read_text."""

    def test_oversized_file_is_skipped_with_error(self, mocker, tmp_path):
        """A file that grew beyond MAX_FILE_SIZE_BYTES between discover and parse
        must be skipped with an error message — not loaded into memory.

        Strategy: temporarily lower ProjectManager.MAX_FILE_SIZE_BYTES to 10
        bytes, then write a 100-byte file. The discover node would have
        accepted it (we bypass discover), but parse_and_store's re-check
        must reject it.
        """
        from workflows.understand_impl.nodes.parse_and_store import (
            node_parse_and_store,
        )
        
        # Write a real 100-byte file.
        big_file = tmp_path / "big.py"
        big_file.write_text("x" * 100 + "\n")  # 101 bytes

        mock_store = MagicMock()
        mocker.patch(
            "workflows.understand_impl.nodes.parse_and_store.GraphStore",
            return_value=mock_store,
        )

        # Patch MAX_FILE_SIZE_BYTES to 10 so the 101-byte file is "too large".
        # We patch it on the ProjectManager CLASS (not instance) because the
        # node accesses it as `ProjectManager.MAX_FILE_SIZE_BYTES`.
        mocker.patch.object(
            ProjectManager,
            "MAX_FILE_SIZE_BYTES",
            10,
        )

        state = _state(tmp_path, [(str(big_file), "big.py", "h", 0.0, 10)],
                       skip_embeddings=True)
        result = node_parse_and_store(state)

        # The file must NOT have been parsed (parsed == 0).
        assert result["files_parsed"] == 0
        # An error about the file size must be in the errors list.
        assert any("too large" in e.lower() for e in result["errors"]), (
            f"errors list must mention 'too large', got: {result['errors']}"
        )


class TestEmbedBatchSizeFromCfg:
    """[v1.4.1 P2-8] Embedding batch size must be read from cfg.understand_embed_batch_size."""

    def test_batch_size_read_from_cfg(self, mocker, tmp_path):
        """_batch_embed_and_store should use cfg.understand_embed_batch_size.

        We verify by patching cfg with a small value (3) and checking that
        embed_texts is called with batches of at most 3 texts.
        """
        from workflows.understand_impl.nodes.parse_and_store import _batch_embed_and_store

        # 7 items, batch_size=3 → 3 batches (3, 3, 1).
        definitions = [
            (f"file{i}.py", {"name": f"fn{i}", "type": "function", "source": "x", "line_start": 1, "line_end": 1})
            for i in range(7)
        ]
        mock_collection = MagicMock()
        mock_pm = MagicMock(project_id="test", is_agent_root=False,
                            artifact_root=tmp_path / ".understand")

        # embed_texts returns the right number of vectors per call.
        # [v1.7] Accepts the new `model` kwarg (per-project embedding model).
        def fake_embed(texts, trace_id="", model="", **kwargs):
            return [[0.1] for _ in texts]
        mocker.patch("core.kgraph.embeddings.embed_texts", side_effect=fake_embed)
        mocker.patch("core.kgraph.embeddings.is_embedding_available", return_value=True)

        # Patch cfg to expose understand_embed_batch_size = 3.
        mocker.patch(
            "workflows.understand_impl.nodes.parse_and_store.cfg.understand_embed_batch_size",
            3,
        )

        vectors, errors = _batch_embed_and_store(
            mock_collection, mock_pm, definitions, [], "t1"
        )

        # 7 vectors should be stored across 3 batches.
        assert vectors == 7
        # 3 upsert calls (one per batch).
        assert mock_collection.upsert.call_count == 3


# ─── [v1.4.2] Additional gap-fill tests ──────────────────────────────────────

class TestCancellationMidParse:
    """[v1.4.2] When cancellation fires mid-parse (not at entry), partial files_parsed."""

    def test_cancellation_mid_parse(self, mocker, tmp_path):
        """Patch is_workflow_cancelled to return False on entry, True thereafter.

        With 11 code files, the every-10-files cancel check fires at idx=10
        AFTER files 0-9 are parsed. Verify status="failed" + 0 < files_parsed < 11.
        """
        from workflows.understand_impl.nodes.parse_and_store import (
            node_parse_and_store,
        )
        
        # 11 code files — idx=10 cancel check fires after 10 files parsed.
        code_files = []
        for i in range(11):
            f = tmp_path / f"f{i}.py"
            f.write_text(f"def fn{i}():\n    pass\n")
            code_files.append((str(f), f"f{i}.py", "h", 0.0, 100))

        mock_store = MagicMock()
        mocker.patch(
            "workflows.understand_impl.nodes.parse_and_store.GraphStore",
            return_value=mock_store,
        )
        mock_pm_class = mocker.patch(
            "workflows.understand_impl.nodes.parse_and_store.ProjectManager",
        )
        mock_pm_class.MAX_FILE_SIZE_BYTES = ProjectManager.MAX_FILE_SIZE_BYTES
        mock_pm_class.return_value.project_id = "test"
        mock_pm_class.return_value.artifact_root = tmp_path / ".understand"
        mock_pm_class.return_value.is_agent_root = False
        mocker.patch(
            "workflows.understand_impl.nodes.parse_and_store.extract_imports",
            return_value=frozenset(),
        )
        mocker.patch(
            "workflows.understand_impl.nodes.parse_and_store.extract_definitions",
            return_value=[],
        )

        # is_workflow_cancelled: False on entry (1st call), True thereafter.
        # The entry check is call 1 (returns False). The idx=10 check is call 2
        # (returns True). Side-effect list pattern: [False, True] — but
        # subsequent calls (if any) would raise StopIteration, so we use a
        # counter-based callable instead.
        call_count = [0]

        def fake_cancelled(tid):
            call_count[0] += 1
            return call_count[0] > 1  # False on entry, True thereafter

        mocker.patch("workflows.base.is_workflow_cancelled", side_effect=fake_cancelled)

        state = _state(tmp_path, code_files, skip_embeddings=True)
        result = node_parse_and_store(state)

        assert result["status"] == "failed"
        # Some files were parsed before the cancel check fired at idx=10.
        assert result["files_parsed"] > 0, "at least one file should parse before mid-parse cancel"
        assert result["files_parsed"] < len(code_files), (
            f"should NOT have parsed all 11 files (cancel fired mid-parse); "
            f"got files_parsed={result['files_parsed']}"
        )
        assert "cancelled" in result["errors"][0].lower()


class TestErrorCapExactly100PlusSummary:
    """[v1.4.2] 150 failing files → errors list has exactly 100 entries + 1 summary."""

    def test_error_cap_at_100(self, mocker, tmp_path):
        from workflows.understand_impl.nodes.parse_and_store import (
            node_parse_and_store, _ERRORS_CAP,
        )
        
        # 150 fake file entries. We create the files on disk so stat() succeeds
        # (skipping the "Stat failed" branch), but patch read_text to raise
        # IOError so each parse produces a "Failed to parse" error.
        files = []
        for i in range(150):
            f = tmp_path / f"f{i}.py"
            f.write_text("x = 1\n")
            files.append((str(f), f"f{i}.py", "h", 0.0, 10))

        mock_store = MagicMock()
        mocker.patch(
            "workflows.understand_impl.nodes.parse_and_store.GraphStore",
            return_value=mock_store,
        )
        mock_pm_class = mocker.patch(
            "workflows.understand_impl.nodes.parse_and_store.ProjectManager",
        )
        mock_pm_class.MAX_FILE_SIZE_BYTES = ProjectManager.MAX_FILE_SIZE_BYTES
        mock_pm_class.return_value.project_id = "test"
        mock_pm_class.return_value.artifact_root = tmp_path / ".understand"
        mock_pm_class.return_value.is_agent_root = False

        # read_text raises — stat succeeds (file exists), then read_text fails
        # so each file produces a "Failed to parse {rel_path}: ..." error.
        def raising_read_text(self, *args, **kwargs):
            raise IOError("simulated read failure")

        mocker.patch("pathlib.Path.read_text", raising_read_text)

        state = _state(tmp_path, files, skip_embeddings=True)
        result = node_parse_and_store(state)

        # The errors list should have EXACTLY _ERRORS_CAP (100) + 1 summary = 101.
        assert len(result["errors"]) == _ERRORS_CAP + 1, (
            f"errors list should be {_ERRORS_CAP + 1} (100 cap + 1 summary), "
            f"got {len(result['errors'])}"
        )
        # First 100 entries are individual failure messages ("Failed to parse ...").
        for i, err in enumerate(result["errors"][:_ERRORS_CAP]):
            assert "Failed to parse" in err or "simulated read failure" in err, (
                f"errors[{i}] should be an individual failure message, got: {err}"
            )
        # Last entry is the "... and N more" summary.
        last = result["errors"][-1]
        assert "more errors" in last.lower() or "capped" in last.lower(), (
            f"last entry should be the cap summary, got: {last}"
        )
        # 150 total failures - 100 kept = 50 dropped.
        assert "50" in last, (
            f"summary should mention 50 dropped errors, got: {last}"
        )


class TestEmbeddingBatchFailureAccumulated:
    """[v1.4.2] Failed embedding batch error is accumulated even if other batches succeed."""

    def test_embedding_batch_failure_accumulated(self, mocker, tmp_path):
        """Mock embed_texts to return None for 1 batch + vectors for the next.

        Verifies the failure is recorded in the errors list even though the
        subsequent batch succeeded — i.e., errors accumulate, they don't get
        overwritten by later successes.
        """
        from workflows.understand_impl.nodes.parse_and_store import (
            _batch_embed_and_store,
        )
        
        # 4 items, batch_size=2 → 2 batches.
        definitions = [
            (f"file{i}.py", {"name": f"fn{i}", "type": "function", "source": "x",
                             "line_start": 1, "line_end": 1})
            for i in range(4)
        ]
        mock_collection = MagicMock()
        mock_pm = MagicMock(project_id="test", is_agent_root=False,
                            artifact_root=tmp_path / ".understand")

        # Patch cfg to use batch_size=2 so we get 2 batches.
        mocker.patch(
            "workflows.understand_impl.nodes.parse_and_store.cfg.understand_embed_batch_size",
            2,
        )
        mocker.patch("core.kgraph.embeddings.is_embedding_available", return_value=True)

        # Batch 1 (2 items) → None (failure). Batch 2 (2 items) → 2 vectors (success).
        mocker.patch(
            "core.kgraph.embeddings.embed_texts",
            side_effect=[None, [[0.1, 0.2], [0.3, 0.4]]],
        )

        vectors, errors = _batch_embed_and_store(
            mock_collection, mock_pm, definitions, [], "t1"
        )

        # Batch 2 succeeded → 2 vectors stored.
        assert vectors == 2, f"expected 2 vectors (batch 2 only), got {vectors}"
        # Batch 1 failed → 1 error in the list.
        assert len(errors) == 1, (
            f"expected 1 error (batch 1 failure), got {len(errors)}: {errors}"
        )
        assert "batch 1" in errors[0].lower(), (
            f"error should reference batch 1, got: {errors[0]}"
        )
        assert "skipped" in errors[0].lower() or "failed" in errors[0].lower(), (
            f"error should mention skip/failure, got: {errors[0]}"
        )
