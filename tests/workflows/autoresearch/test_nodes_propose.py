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
                   return_value={"status": "success", "response": '{"x": 1}'}) as m:
            out = _call_planner("sys", "user", tid="t1")
        assert out == '{"x": 1}'
        m.assert_called_once()

    def test_retry_then_success(self):
        from workflows.autoresearch_impl.nodes.propose import _call_planner
        responses = [
            {"status": "error", "error": "blip"},
            {"status": "success", "response": "ok"},
        ]
        with patch("tools.agent.agent", side_effect=responses) as m, \
             patch("time.sleep"):  # skip backoff
            out = _call_planner("sys", "user", tid="t1")
        assert out == "ok"
        assert m.call_count == 2

    def test_all_retries_fail_raises_runtimeerror(self):
        from workflows.autoresearch_impl.nodes.propose import _call_planner
        with patch("tools.agent.agent", side_effect=RuntimeError("dead")) as m, \
             patch("time.sleep"):
            with pytest.raises(RuntimeError, match="3 attempts"):
                _call_planner("sys", "user", tid="t1")
        assert m.call_count == 3


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
        with patch("workflows.autoresearch_impl.nodes.propose._call_planner",
                   return_value=proposal_json):
            result = node_propose(state)
        ce = result["current_experiment"]
        assert ce["iteration"] == 1
        assert ce["description"] == "increase lr"
        assert ce["new_content"] == "print('new')"  # .strip() drops trailing \n
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
            return proposal_json

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
        from workflows.autoresearch_impl.nodes.modify import _atomic_write
        target = tmp_path / "out.txt"
        with patch("workflows.autoresearch_impl.nodes.modify.os.replace",
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
