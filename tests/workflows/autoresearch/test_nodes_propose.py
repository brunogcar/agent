"""tests/workflows/autoresearch/test_nodes_propose.py

Per-node tests for propose + modify (and their helpers).

Coverage:
  _format_history   — empty, 5 entries, >20 cap, most-recent-first ordering
  _parse_proposal   — valid JSON, unparseable fallback, missing keys defaults
  _call_planner     — success, retry-then-success, all-retries-fail → RuntimeError
  node_propose      — happy path, LLM failure → status="failed",
                      target file cap (truncation at autocode_max_file_chars)
  _atomic_write     — success, write failure → tempfile cleaned up
  node_modify       — success, empty new_content → failed,
                      path traversal → blocked, protected file → blocked

[v1.3 tests] New file — propose had ZERO dedicated tests before this file;
modify had 2 inline tests in test_loop_integration.py (now merged here).
The helpers `_call_planner`, `_parse_proposal`, `_format_history`,
`_atomic_write` were entirely untested.
"""
from __future__ import annotations

import json
from unittest.mock import patch, MagicMock

import pytest


# ---------------------------------------------------------------------------
# _format_history (helper)
# ---------------------------------------------------------------------------


class TestFormatHistory:
    def test_empty_history(self):
        from workflows.autoresearch_impl.nodes.propose import _format_history
        out = _format_history([], "val_bpb")
        assert "no prior experiments" in out

    def test_five_entries_most_recent_first(self):
        from workflows.autoresearch_impl.nodes.propose import _format_history
        hist = [{"iteration": i, "description": f"d{i}", "metric": 0.1 * i,
                 "status": "keep"} for i in range(1, 6)]
        out = _format_history(hist, "val_bpb")
        # iteration 5 (last in history) must appear first (most-recent-first).
        first_line = out.splitlines()[0]
        assert "#5" in first_line
        assert "#1" in out.splitlines()[-1]

    def test_caps_at_20_entries(self):
        from workflows.autoresearch_impl.nodes.propose import _format_history
        hist = [{"iteration": i, "description": f"d{i}", "metric": 0.1,
                 "status": "keep"} for i in range(1, 31)]
        out = _format_history(hist, "val_bpb", limit=20)
        # Most recent 20 = iterations 11-30. Iteration 1-10 should NOT appear.
        assert "#30" in out
        assert "#11" in out
        assert "#10" not in out

    def test_most_recent_first_ordering(self):
        from workflows.autoresearch_impl.nodes.propose import _format_history
        hist = [
            {"iteration": 1, "description": "old", "metric": 0.5, "status": "keep"},
            {"iteration": 2, "description": "new", "metric": 0.4, "status": "keep"},
        ]
        out = _format_history(hist, "val_bpb")
        assert out.splitlines()[0].startswith("  #2")


# ---------------------------------------------------------------------------
# _parse_proposal (helper)
# ---------------------------------------------------------------------------


class TestParseProposal:
    def test_valid_json(self):
        from workflows.autoresearch_impl.nodes.propose import _parse_proposal
        raw = json.dumps({"description": "x", "rationale": "y", "new_content": "z"})
        out = _parse_proposal(raw)
        assert out == {"description": "x", "rationale": "y", "new_content": "z"}

    def test_unparseable_returns_empty_defaults(self):
        from workflows.autoresearch_impl.nodes.propose import _parse_proposal
        # extract_json returns {} on failure (not None), so _parse_proposal
        # takes the dict path with defaults rather than the explicit fallback.
        out = _parse_proposal("not json {{{")
        assert out == {"description": "", "rationale": "", "new_content": ""}

    def test_missing_keys_get_defaults(self):
        from workflows.autoresearch_impl.nodes.propose import _parse_proposal
        out = _parse_proposal('{"description": "only desc"}')
        assert out["description"] == "only desc"
        assert out["rationale"] == ""
        assert out["new_content"] == ""


# ---------------------------------------------------------------------------
# _call_planner (helper)
# ---------------------------------------------------------------------------


class TestCallPlanner:
    def test_success_returns_response(self):
        from workflows.autoresearch_impl.nodes.propose import _call_planner
        with patch("tools.agent.agent",
                   return_value={"status": "success", "response": '{"x": 1}',
                                 "usage": {"total": 42}}) as m:
            out, usage = _call_planner("sys", "user", tid="t1")
        assert out == '{"x": 1}'
        assert usage == {"total": 42}
        m.assert_called_once()

    def test_retry_then_success(self):
        from workflows.autoresearch_impl.nodes.propose import _call_planner
        responses = [
            {"status": "error", "error": "blip"},
            {"status": "success", "response": "ok", "usage": {"total": 7}},
        ]
        with patch("tools.agent.agent", side_effect=responses) as m, \
             patch("time.sleep"):  # skip backoff
            out, usage = _call_planner("sys", "user", tid="t1")
        assert out == "ok"
        assert usage == {"total": 7}
        assert m.call_count == 2

    def test_all_retries_fail_raises_runtimeerror(self):
        from workflows.autoresearch_impl.nodes.propose import _call_planner
        with patch("tools.agent.agent", side_effect=RuntimeError("dead")) as m, \
             patch("time.sleep"):
            with pytest.raises(RuntimeError, match="3 attempts"):
                _call_planner("sys", "user", tid="t1")
        assert m.call_count == 3

    def test_missing_usage_defaults_to_empty_dict(self):
        """[v1.8 N6] When subagent doesn't report usage, return ({}, {})."""
        from workflows.autoresearch_impl.nodes.propose import _call_planner
        with patch("tools.agent.agent",
                   return_value={"status": "success", "response": "ok"}):
            out, usage = _call_planner("sys", "user", tid="t1")
        assert out == "ok"
        assert usage == {}


# ---------------------------------------------------------------------------
# node_propose
# ---------------------------------------------------------------------------


class TestNodePropose:
    def test_happy_path_returns_proposal_with_iteration(self, ar_state, tmp_path):
        from workflows.autoresearch_impl.nodes.propose import node_propose
        (tmp_path / "train.py").write_text("print('hi')\n", encoding="utf-8")
        state = dict(ar_state)
        state["experiment_count"] = 0
        proposal_json = json.dumps({
            "description": "increase lr",
            "rationale": "faster convergence",
            "new_content": "print('new')\n",
        })
        # [v1.8 N6] _call_planner now returns (response, usage) tuple.
        with patch("workflows.autoresearch_impl.nodes.propose._call_planner",
                   return_value=(proposal_json, {"total": 1234})):
            result = node_propose(state)
        ce = result["current_experiment"]
        assert ce["iteration"] == 1
        assert ce["description"] == "increase lr"
        assert ce["new_content"] == "print('new')"  # .strip() drops trailing \n
        assert ce["tokens"] == 1234  # [v1.8 N6] total tokens captured
        assert result["status"] == "running"

    def test_llm_failure_returns_failed_status(self, ar_state):
        from workflows.autoresearch_impl.nodes.propose import node_propose
        with patch("workflows.autoresearch_impl.nodes.propose._call_planner",
                   side_effect=RuntimeError("Subagent planner failed: down")):
            result = node_propose(dict(ar_state))
        assert result["status"] == "failed"
        assert "planner LLM call failed" in result["error"]
        assert result["current_experiment"]["iteration"] == 1

    def test_target_file_cap_truncates_long_content(self, ar_state, tmp_path, monkeypatch):
        from workflows.autoresearch_impl.nodes.propose import node_propose
        # Cap to a tiny value so we can trigger truncation with a small file.
        import core.config
        monkeypatch.setattr(core.config.cfg, "autocode_max_file_chars", 100)
        big = "x" * 500
        (tmp_path / "train.py").write_text(big, encoding="utf-8")
        proposal_json = json.dumps({
            "description": "d", "rationale": "r", "new_content": "n",
        })
        captured = {}

        def _fake_call(system, user, tid=""):
            captured["user"] = user
            # [v1.8 N6] _call_planner now returns (response, usage) tuple.
            return proposal_json, {"total": 0}

        with patch("workflows.autoresearch_impl.nodes.propose._call_planner",
                   side_effect=_fake_call):
            node_propose(dict(ar_state))
        assert "[TRUNCATED" in captured["user"]
        assert captured["user"].count("x") < 500


# ---------------------------------------------------------------------------
# _atomic_write (helper)
# ---------------------------------------------------------------------------


class TestAtomicWrite:
    def test_write_succeeds(self, tmp_path):
        from workflows.autoresearch_impl.nodes.modify import _atomic_write
        target = tmp_path / "out.txt"
        _atomic_write(target, "hello\n")
        assert target.read_text(encoding="utf-8") == "hello\n"

    def test_write_failure_cleans_tempfile(self, tmp_path):
        # [v1.10 / Phase A] _atomic_write is now an alias for
        # core.atomic_write.atomic_write. The implementation lives in
        # core/atomic_write.py, so we patch os.replace there (was:
        # workflows.autoresearch_impl.nodes.modify.os.replace).
        from workflows.autoresearch_impl.nodes.modify import _atomic_write
        target = tmp_path / "out.txt"
        with patch("core.atomic_write.os.replace",
                   side_effect=OSError("disk full")):
            with pytest.raises(OSError):
                _atomic_write(target, "hello\n")
        leftovers = [p.name for p in tmp_path.iterdir() if p.name.endswith(".tmp")]
        assert leftovers == [], f"tempfile leaked: {leftovers}"


# ---------------------------------------------------------------------------
# node_modify
# ---------------------------------------------------------------------------


class TestNodeModify:
    def test_writes_new_content_atomically(self, ar_state, tmp_path):
        from workflows.autoresearch_impl.nodes.modify import node_modify
        target = tmp_path / "train.py"
        target.write_text("old\n", encoding="utf-8")
        state = dict(ar_state)
        state.update({
            "target_file": "train.py",
            "project_root": str(tmp_path),
            "current_experiment": {
                "iteration": 1, "description": "rewrite",
                "new_content": "print('new')\n",
            },
        })
        result = node_modify(state)
        assert result["status"] == "running"
        assert target.read_text(encoding="utf-8") == "print('new')\n"

    def test_empty_new_content_returns_failed(self, ar_state):
        from workflows.autoresearch_impl.nodes.modify import node_modify
        state = dict(ar_state)
        state.update({
            "current_experiment": {
                "iteration": 1, "description": "broken", "new_content": "",
            },
        })
        result = node_modify(state)
        assert result["status"] == "failed"
        assert "empty" in result["error"].lower()

    def test_path_traversal_is_blocked(self, ar_state, tmp_path):
        from workflows.autoresearch_impl.nodes.modify import node_modify
        state = dict(ar_state)
        state.update({
            "target_file": "../../etc/passwd",
            "project_root": str(tmp_path),
            "current_experiment": {
                "iteration": 1, "description": "evil", "new_content": "hax\n",
            },
        })
        result = node_modify(state)
        assert result["status"] == "failed"
        assert "path traversal" in result["error"]

    def test_protected_file_is_blocked(self, ar_state, tmp_path):
        from workflows.autoresearch_impl.nodes.modify import node_modify
        target = tmp_path / "train.py"
        target.write_text("old\n", encoding="utf-8")
        state = dict(ar_state)
        state.update({
            "target_file": "train.py",
            "project_root": str(tmp_path),
            "current_experiment": {
                "iteration": 1, "description": "x", "new_content": "y\n",
            },
        })
        with patch("core.config.cfg.is_protected", return_value=True):
            result = node_modify(state)
        assert result["status"] == "failed"
        assert "protected" in result["error"]


# ===========================================================================
# [v1.9 B4] _call_planner exception scope (deepseek P2 2.4)
# ===========================================================================


class TestCallPlannerExceptionScope:
    """[v1.9 B4] _call_planner catches only transient failure types
    (RuntimeError, ConnectionError, TimeoutError, OSError, ValueError).
    KeyboardInterrupt, SystemExit, ImportError, AttributeError propagate.
    """

    def test_call_planner_does_not_swallow_keyboard_interrupt(self):
        """Patch tools.agent.agent to raise KeyboardInterrupt → _call_planner
        propagates it (doesn't retry, doesn't swallow)."""
        from workflows.autoresearch_impl.nodes.propose import _call_planner
        with patch("tools.agent.agent", side_effect=KeyboardInterrupt), \
             patch("time.sleep"):  # skip backoff if it DID retry
            with pytest.raises(KeyboardInterrupt):
                _call_planner("sys", "user", tid="t1")

    def test_call_planner_does_not_swallow_import_error(self):
        """ImportError indicates a bug, not a transient failure — must propagate."""
        from workflows.autoresearch_impl.nodes.propose import _call_planner
        with patch("tools.agent.agent", side_effect=ImportError("missing module")), \
             patch("time.sleep"):
            with pytest.raises(ImportError):
                _call_planner("sys", "user", tid="t1")

    def test_call_planner_retries_runtime_error(self):
        """RuntimeError IS a transient type — must be retried 3× then raised."""
        from workflows.autoresearch_impl.nodes.propose import _call_planner
        with patch("tools.agent.agent", side_effect=RuntimeError("transient")), \
             patch("time.sleep"):
            with pytest.raises(RuntimeError, match="3 attempts"):
                _call_planner("sys", "user", tid="t1")


# ===========================================================================
# [v1.9 C6] Parallel propose stagger (qwen P2-6)
# ===========================================================================


class TestParallelProposeStagger:
    """[v1.9 C6] Each parallel _call_planner call sleeps i*0.5s (capped at
    2.0s) before submitting. Prevents thundering-herd 429s on rate-limited
    providers.
    """

    def test_parallel_propose_staggers_calls(self, ar_state, tmp_path):
        """Patch time.sleep to record durations — verify sleeps are
        [0, 0.5, 1.0, 1.5, 2.0, 2.0, 2.0, 2.0] for N=8 (capped at 2.0)."""
        from workflows.autoresearch_impl.nodes.propose import node_propose
        (tmp_path / "train.py").write_text("print('hi')\n", encoding="utf-8")
        state = dict(ar_state)
        state["parallel_count"] = 8
        state["experiment_count"] = 0

        sleep_durations = []
        proposal_json = json.dumps({
            "description": "d", "rationale": "r", "new_content": "print('new')\n",
        })

        def fake_sleep(seconds):
            sleep_durations.append(seconds)

        # Each call returns a successful tuple.
        def fake_call(system, user, tid=""):
            return proposal_json, {"total": 0}

        with patch("workflows.autoresearch_impl.nodes.propose._call_planner",
                   side_effect=fake_call), \
             patch("time.sleep", side_effect=fake_sleep):
            result = node_propose(state)

        # The stagger happens INSIDE the submitted function, so we expect 8
        # sleeps (one per parallel call). i=0 → 0s (no sleep), i=1 → 0.5s,
        # i=2 → 1.0s, i=3 → 1.5s, i=4..7 → 2.0s (capped).
        # Note: the order depends on thread scheduling, so we sort + compare.
        # i=0's stagger is 0, so it might not call sleep at all (we skip sleep
        # when stagger == 0). So we expect 7 non-zero sleeps OR 8 sleeps with
        # one being 0. Sort + filter zeros, then check the non-zero set.
        non_zero = sorted(s for s in sleep_durations if s > 0)
        # Expected non-zero staggers: 0.5, 1.0, 1.5, 2.0, 2.0, 2.0, 2.0 (7 values).
        assert len(non_zero) == 7, (
            f"expected 7 non-zero staggers for N=8 (i=0 skips sleep), "
            f"got {len(non_zero)}: {non_zero}"
        )
        expected = [0.5, 1.0, 1.5, 2.0, 2.0, 2.0, 2.0]
        for actual, exp in zip(non_zero, expected):
            assert abs(actual - exp) < 0.01, (
                f"stagger mismatch: expected {exp}, got {actual}"
            )


# ===========================================================================
# [v1.9 D4] Variant seeds for parallel propose (minimax Risk #3)
# ===========================================================================


class TestParallelVariantSeeds:
    """[v1.9 D4] Parallel _call_planner calls get a distinct variant_seed
    appended to the prompt. Guarantees diversity even at temperature=0.
    """

    def test_parallel_propose_includes_variant_seed(self, ar_state, tmp_path):
        """Patch _call_planner to record the task arg, verify each of the N
        calls has a distinct '--- VARIANT 0/1/2 ---' marker. Single path
        (parallel_count=1) has NO variant marker."""
        from workflows.autoresearch_impl.nodes.propose import node_propose
        (tmp_path / "train.py").write_text("print('hi')\n", encoding="utf-8")

        captured_tasks = []
        proposal_json = json.dumps({
            "description": "d", "rationale": "r", "new_content": "print('new')\n",
        })

        def fake_call(system, user, tid=""):
            captured_tasks.append(user)
            return proposal_json, {"total": 0}

        # Parallel path — 3 calls, each with a distinct variant marker.
        state = dict(ar_state)
        state["parallel_count"] = 3
        state["experiment_count"] = 0
        with patch("workflows.autoresearch_impl.nodes.propose._call_planner",
                   side_effect=fake_call), \
             patch("time.sleep"):
            node_propose(state)

        assert len(captured_tasks) == 3
        # Each call must have a distinct VARIANT marker.
        markers = []
        for task in captured_tasks:
            # Look for "--- VARIANT 0 ---", "--- VARIANT 1 ---", etc.
            for i in range(3):
                if f"VARIANT {i}" in task:
                    markers.append(i)
                    break
        assert sorted(markers) == [0, 1, 2], (
            f"expected variant markers [0,1,2], got {markers}"
        )

    def test_single_path_has_no_variant_marker(self, ar_state, tmp_path):
        """Single path (parallel_count=1) must NOT have a variant marker."""
        from workflows.autoresearch_impl.nodes.propose import node_propose
        (tmp_path / "train.py").write_text("print('hi')\n", encoding="utf-8")

        captured_task = []
        proposal_json = json.dumps({
            "description": "d", "rationale": "r", "new_content": "print('new')\n",
        })

        def fake_call(system, user, tid=""):
            captured_task.append(user)
            return proposal_json, {"total": 0}

        state = dict(ar_state)
        state["parallel_count"] = 1
        state["experiment_count"] = 0
        with patch("workflows.autoresearch_impl.nodes.propose._call_planner",
                   side_effect=fake_call):
            node_propose(state)

        assert len(captured_task) == 1
        assert "VARIANT" not in captured_task[0], (
            "single path must NOT have a variant marker"
        )


# ===========================================================================
# [v1.9 D6] Memory recall tag filter (minimax Risk #5)
# ===========================================================================


class TestMemoryRecallTagFilter:
    """[v1.9 D6] node_propose's memory.recall call passes
    tags_filter='source:autoresearch' so only autoresearch-stored memories
    are surfaced (not unrelated procedural memories from other workflows).
    """

    def test_memory_recall_filters_by_source_tag(self, ar_state, tmp_path):
        """Patch core.memory_engine.memory.recall to record kwargs, verify
        tags_filter='source:autoresearch' is passed."""
        from workflows.autoresearch_impl.nodes.propose import node_propose
        (tmp_path / "train.py").write_text("print('hi')\n", encoding="utf-8")

        # Inject a fake memory_engine module.
        mock_mem = MagicMock()
        mock_mem.recall.return_value = []
        fake_module = MagicMock()
        fake_module.memory = mock_mem

        state = dict(ar_state)
        state["experiment_count"] = 0
        # [v1.9 hardening] Patch _call_planner so node_propose doesn't fire a
        # real LLM call (was 8s; now <0.5s). The planner returns a minimal
        # valid proposal JSON; node_propose parses it without ever calling
        # tools.agent.agent.
        fake_proposal = '{"description": "test", "rationale": "test", "new_content": "print(1)"}'
        with patch.dict("sys.modules", {"core.memory_engine": fake_module}), \
             patch("workflows.autoresearch_impl.nodes.propose._call_planner",
                   return_value=(fake_proposal, {"total": 0})):
            node_propose(state)

        mock_mem.recall.assert_called()
        call_kwargs = mock_mem.recall.call_args
        # tags_filter must be passed (either as kwarg or positional).
        tags_filter = call_kwargs.kwargs.get("tags_filter") or call_kwargs[1].get("tags_filter", "")
        assert tags_filter == "source:autoresearch", (
            f"expected tags_filter='source:autoresearch', got {tags_filter!r}"
        )
