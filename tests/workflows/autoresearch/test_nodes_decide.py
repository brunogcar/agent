"""tests/workflows/autoresearch/test_nodes_decide.py

Per-node tests for decide + log (and their helpers).

Coverage:
  _is_improvement   — lower / higher / equal / unknown-direction default
  _git_commit       — success returns SHA, commit-fails → "", rev-parse-fails → ""
  _git_reset_hard   — success, no project_root → False, no .git → False (v1.3 P1-4)
  node_decide       — improvement keeps + commits, no-improvement discards + resets,
                      prior failure discards, empty SHA discards (v1.3 P1-1),
                      status reset to "running" on every path
  node_log          — ledger row written, history appended, history cap at 100,
                      current_experiment cleared

[v1.3 tests] New file — decide + log helpers were entirely untested before
this file. The 2 inline decide tests from test_loop_integration.py are
merged here (test_decide_keep_updates_current_best, test_decide_discard_*).
"""
from __future__ import annotations

from unittest.mock import patch, MagicMock

import pytest


# ---------------------------------------------------------------------------
# _is_improvement (helper)
# ---------------------------------------------------------------------------


class TestIsImprovement:
    def test_lower_direction_new_below_best_is_improvement(self):
        from workflows.autoresearch_impl.nodes.decide import _is_improvement
        assert _is_improvement(0.4, 0.5, "lower") is True

    def test_lower_direction_new_above_best_is_not_improvement(self):
        from workflows.autoresearch_impl.nodes.decide import _is_improvement
        assert _is_improvement(0.6, 0.5, "lower") is False

    def test_higher_direction_new_above_best_is_improvement(self):
        from workflows.autoresearch_impl.nodes.decide import _is_improvement
        assert _is_improvement(0.6, 0.5, "higher") is True

    def test_equal_is_not_improvement(self):
        from workflows.autoresearch_impl.nodes.decide import _is_improvement
        assert _is_improvement(0.5, 0.5, "lower") is False
        assert _is_improvement(0.5, 0.5, "higher") is False

    def test_unknown_direction_defaults_to_lower(self):
        from workflows.autoresearch_impl.nodes.decide import _is_improvement
        assert _is_improvement(0.4, 0.5, "sideways") is True
        assert _is_improvement(0.6, 0.5, "") is False


# ---------------------------------------------------------------------------
# _git_commit (helper)
# ---------------------------------------------------------------------------


class TestGitCommit:
    def test_success_returns_short_sha(self, tmp_path):
        """[v1.10 / Phase B] _git_commit is now a wrapper around
        tools.git_ops.workflow_helpers.commit (imported as _git_commit_w).
        Patch _git_commit_w to return a dict, verify the wrapper extracts sha."""
        from workflows.autoresearch_impl.nodes.decide import _git_commit
        with patch("workflows.autoresearch_impl.nodes.decide._git_commit_w",
                   return_value={"committed": True, "sha": "abc1234"}) as m:
            sha = _git_commit("msg", str(tmp_path), "tid", "train.py")
        assert sha == "abc1234"
        m.assert_called_once_with(str(tmp_path), "msg", "train.py", "tid")

    def test_commit_fails_returns_empty(self, tmp_path):
        """[v1.10 / Phase B] When commit returns {committed: False}, wrapper returns ""."""
        from workflows.autoresearch_impl.nodes.decide import _git_commit
        with patch("workflows.autoresearch_impl.nodes.decide._git_commit_w",
                   return_value={"committed": False, "sha": "", "reason": "commit failed"}):
            sha = _git_commit("msg", str(tmp_path), "tid", "train.py")
        assert sha == ""

    def test_rev_parse_fails_returns_empty(self, tmp_path):
        """[v1.10 / Phase B] committed=True but sha="" → wrapper returns "".

        (rev-parse failure in workflow_helpers.commit yields {committed: True,
        sha: ""} — unusual but the wrapper handles it by returning the empty string.)
        """
        from workflows.autoresearch_impl.nodes.decide import _git_commit
        with patch("workflows.autoresearch_impl.nodes.decide._git_commit_w",
                   return_value={"committed": True, "sha": ""}):
            sha = _git_commit("msg", str(tmp_path), "tid", "train.py")
        assert sha == ""


# ---------------------------------------------------------------------------
# _git_reset_hard (helper)
# ---------------------------------------------------------------------------


class TestGitResetHard:
    def test_no_project_root_returns_false(self):
        """[v1.10 / Phase B] _git_reset_hard is now imported from
        tools.git_ops.workflow_helpers. When project_root is empty, it
        returns False without calling _git."""
        from workflows.autoresearch_impl.nodes.decide import _git_reset_hard
        # No patch — call the real function. With project_root="", it should
        # return False immediately (no _git call). Patch _git to verify it's
        # NOT called.
        with patch("tools.git_ops.workflow_helpers._git") as m_git:
            assert _git_reset_hard("", "tid") is False
        m_git.assert_not_called()

    def test_no_git_directory_returns_false(self, tmp_path):
        """[v1.10 / Phase B] workflow_helpers.reset_hard checks toplevel;
        non-repo dir → _git rev-parse fails → returns False."""
        from workflows.autoresearch_impl.nodes.decide import _git_reset_hard
        # _git (rev-parse --show-toplevel) returns rc=1 → reset_hard returns False.
        with patch("tools.git_ops.workflow_helpers._git",
                   return_value=(1, "", "not a git repo")):
            assert _git_reset_hard(str(tmp_path), "tid") is False

    def test_success_returns_true(self, tmp_path):
        """[v1.10 / Phase B] Toplevel matches → reset + clean succeed → True."""
        from workflows.autoresearch_impl.nodes.decide import _git_reset_hard
        # 3 calls: rev-parse (returns tmp_path), reset --hard, clean -fd.
        side = [
            (0, str(tmp_path) + "\n", ""),
            (0, "", ""),
            (0, "", ""),
        ]
        with patch("tools.git_ops.workflow_helpers._git", side_effect=side) as m:
            assert _git_reset_hard(str(tmp_path), "tid") is True
        assert m.call_count == 3


# ---------------------------------------------------------------------------
# node_decide
# ---------------------------------------------------------------------------


class TestNodeDecide:
    def test_improvement_commits_and_updates_current_best(self, ar_state):
        from workflows.autoresearch_impl.nodes.decide import node_decide
        state = dict(ar_state)
        state.update({
            "current_best": 0.5, "current_metric": 0.4,
            "metric_direction": "lower",
            "current_experiment": {"iteration": 1, "description": "good"},
        })
        with patch("workflows.autoresearch_impl.nodes.decide._git_commit",
                   return_value="abc1234") as mock_commit, \
             patch("workflows.autoresearch_impl.nodes.decide._git_reset_hard") as mock_reset:
            result = node_decide(state)
        assert result["current_best"] == 0.4
        assert result["current_experiment"]["status"] == "keep"
        assert result["current_experiment"]["commit"] == "abc1234"
        assert result["status"] == "running"  # reset on every path
        mock_commit.assert_called_once()
        mock_reset.assert_not_called()

    def test_no_improvement_discards_and_resets(self, ar_state):
        from workflows.autoresearch_impl.nodes.decide import node_decide
        state = dict(ar_state)
        state.update({
            "current_best": 0.5, "current_metric": 0.6,
            "metric_direction": "lower",
            "current_experiment": {"iteration": 1, "description": "bad"},
        })
        with patch("workflows.autoresearch_impl.nodes.decide._git_commit") as mock_commit, \
             patch("workflows.autoresearch_impl.nodes.decide._git_reset_hard",
                   return_value=True) as mock_reset:
            result = node_decide(state)
        assert result["current_best"] == 0.5  # unchanged
        assert result["current_experiment"]["status"] == "discard"
        assert result["current_experiment"]["commit"] == ""
        assert result["status"] == "running"  # reset on every path
        mock_commit.assert_not_called()
        mock_reset.assert_called_once()

    def test_prior_failure_discards(self, ar_state):
        from workflows.autoresearch_impl.nodes.decide import node_decide
        state = dict(ar_state)
        state.update({
            "status": "failed",  # prior node failed
            "current_best": 0.5, "current_metric": 0.4,  # would be improvement
            "metric_direction": "lower",
            "current_experiment": {"iteration": 1, "description": "x"},
        })
        with patch("workflows.autoresearch_impl.nodes.decide._git_commit") as mock_commit, \
             patch("workflows.autoresearch_impl.nodes.decide._git_reset_hard",
                   return_value=True) as mock_reset:
            result = node_decide(state)
        assert result["current_experiment"]["status"] == "discard"
        assert result["current_best"] == 0.5  # unchanged
        assert result["status"] == "running"  # reset on every path
        mock_commit.assert_not_called()
        mock_reset.assert_called_once()

    def test_empty_sha_discards_despite_improvement(self, ar_state):
        """[v1.3 P1-1] Empty SHA (git commit failed) → discard, don't update best."""
        from workflows.autoresearch_impl.nodes.decide import node_decide
        state = dict(ar_state)
        state.update({
            "current_best": 0.5, "current_metric": 0.4,
            "metric_direction": "lower",
            "current_experiment": {"iteration": 1, "description": "x"},
        })
        with patch("workflows.autoresearch_impl.nodes.decide._git_commit",
                   return_value="") as mock_commit, \
             patch("workflows.autoresearch_impl.nodes.decide._git_reset_hard",
                   return_value=True) as mock_reset:
            result = node_decide(state)
        assert result["current_best"] == 0.5  # NOT updated despite improvement
        assert result["current_experiment"]["status"] == "discard"
        assert result["current_experiment"]["commit"] == ""
        mock_commit.assert_called_once()
        mock_reset.assert_called_once()


# ---------------------------------------------------------------------------
# node_log
# ---------------------------------------------------------------------------


class TestNodeLog:
    def _state(self, ar_state, tmp_path):
        """Build a state with a pre-existing ledger + experiment to log."""
        results_path = tmp_path / "results.tsv"
        results_path.write_text(
            "iteration\tcommit\tmetric\tstatus\tdescription\n", encoding="utf-8",
        )
        state = dict(ar_state)
        state.update({
            "results_path": str(results_path),
            "experiment_count": 0,
            "experiment_history": [],
            "current_experiment": {
                "iteration": 1, "description": "test experiment",
                "metric": 0.45, "status": "keep", "commit": "abc1234",
            },
        })
        return state, results_path

    def test_writes_row_with_correct_status_commit_metric(self, ar_state, tmp_path):
        from workflows.autoresearch_impl.nodes.log import node_log
        state, results_path = self._state(ar_state, tmp_path)
        node_log(state)
        content = results_path.read_text(encoding="utf-8")
        assert "1\tabc1234\t0.45\tkeep\ttest experiment" in content

    def test_appends_to_experiment_history(self, ar_state, tmp_path):
        from workflows.autoresearch_impl.nodes.log import node_log
        state, _ = self._state(ar_state, tmp_path)
        result = node_log(state)
        assert len(result["experiment_history"]) == 1
        assert result["experiment_history"][0]["iteration"] == 1

    def test_current_experiment_cleared_after_log(self, ar_state, tmp_path):
        from workflows.autoresearch_impl.nodes.log import node_log
        state, _ = self._state(ar_state, tmp_path)
        result = node_log(state)
        assert result["current_experiment"] == {}
        assert result["experiment_count"] == 1

    def test_history_capped_at_100(self, ar_state, tmp_path):
        from workflows.autoresearch_impl.nodes.log import node_log
        state, _ = self._state(ar_state, tmp_path)
        # Pre-fill 100 entries — after appending one more, must still be 100.
        state["experiment_history"] = [
            {"iteration": i, "description": f"old{i}", "metric": 0.1,
             "status": "discard", "commit": ""}
            for i in range(100)
        ]
        result = node_log(state)
        assert len(result["experiment_history"]) == 100
        # Most-recent (the just-appended entry) must be present.
        assert result["experiment_history"][-1]["iteration"] == 1


# ===========================================================================
# [v1.9 A1] Parallel cross-run learning gate (minimax Bug #1)
# ===========================================================================


class TestParallelCrossRunMemoryGate:
    """[v1.9 A1] _record_failure_memory must NOT be called for parallel
    losers that DID improve over the OUTER current_best (but lost to the
    winner). Pre-v1.9, every loser got the call → procedural memory was
    poisoned with false failures.
    """

    def _state_with_3_experiments(self, ar_state, tmp_path, metrics):
        """Build a state with 3 proposals + temp files + metrics for decide."""
        parallel_dir = tmp_path / ".autoresearch" / "parallel"
        proposals = []
        for i in range(3):
            exp_dir = parallel_dir / str(i)
            exp_dir.mkdir(parents=True, exist_ok=True)
            (exp_dir / "train.py").write_text(f"# version {i}\n", encoding="utf-8")
            proposals.append({
                "iteration": i + 1,
                "description": f"change {i}",
                "new_content": f"# version {i}\n",
                "content_hash": f"hash{i}",
            })
        state = dict(ar_state)
        state["parallel_count"] = 3
        state["target_file"] = "train.py"
        state["project_root"] = str(tmp_path)
        state["metric_direction"] = "lower"
        state["current_best"] = 0.5
        state["current_experiments"] = proposals
        state["current_metrics"] = metrics
        return state, parallel_dir

    def test_parallel_decide_does_not_record_memory_for_improving_loser(
        self, ar_state, tmp_path,
    ):
        """3 proposals, metrics=[0.45, 0.40, 0.50], current_best=0.5, lower.

        Winner is idx 1 (0.40, best). Loser 0 (0.45) IS an improvement over
        0.5 → must NOT call _record_failure_memory. Loser 2 (0.50) is NOT an
        improvement → MUST call _record_failure_memory.
        """
        from workflows.autoresearch_impl.nodes.decide import node_decide
        state, parallel_dir = self._state_with_3_experiments(
            ar_state, tmp_path, [0.45, 0.40, 0.50],
        )

        with patch("workflows.autoresearch_impl.nodes.decide._git_commit",
                   return_value="abc1234"), \
             patch("workflows.autoresearch_impl.nodes.decide._record_failure_memory") as mock_mem:
            node_decide(state)

        # _record_failure_memory called exactly once — for loser 2 (0.50, NOT
        # an improvement over 0.5). Loser 0 (0.45, IS an improvement) was skipped.
        assert mock_mem.call_count == 1
        # Verify the call was for proposal idx 2 (metric 0.50).
        called_proposal = mock_mem.call_args[0][0]
        called_metric = mock_mem.call_args[0][2]
        assert called_metric == 0.50
        assert called_proposal.get("iteration") == 3  # idx 2 → iteration 3


# ===========================================================================
# [v1.9 A3] Atomic parallel winner copy (minimax Bug #3)
# ===========================================================================


class TestAtomicParallelWinnerCopy:
    """[v1.9 A3] Parallel winner copy uses _atomic_write (was: non-atomic
    write_text). SIGKILL/OOM mid-write left target_file empty/partial.
    """

    def test_parallel_winner_copy_is_atomic(self, ar_state, tmp_path):
        """Patch _atomic_write to assert it's called with the winner's content
        + the real path. Mock the actual write so we don't need a real file."""
        from workflows.autoresearch_impl.nodes.decide import node_decide
        parallel_dir = tmp_path / ".autoresearch" / "parallel"
        proposals = []
        for i in range(3):
            exp_dir = parallel_dir / str(i)
            exp_dir.mkdir(parents=True, exist_ok=True)
            (exp_dir / "train.py").write_text(f"# version {i}\n", encoding="utf-8")
            proposals.append({
                "iteration": i + 1, "description": f"change {i}",
                "new_content": f"# version {i}\n", "content_hash": f"hash{i}",
            })
        state = dict(ar_state)
        state["parallel_count"] = 3
        state["target_file"] = "train.py"
        state["project_root"] = str(tmp_path)
        state["metric_direction"] = "lower"
        state["current_best"] = 0.5
        state["current_experiments"] = proposals
        state["current_metrics"] = [0.45, 0.40, 0.50]  # winner = idx 1 (0.40)

        with patch("workflows.autoresearch_impl.nodes.decide._git_commit",
                   return_value="abc1234"), \
             patch("workflows.autoresearch_impl.nodes.decide._atomic_write") as mock_atomic:
            node_decide(state)

        # _atomic_write was called once with the real path + winner's content.
        mock_atomic.assert_called_once()
        call_args = mock_atomic.call_args[0]
        real_path, content = call_args[0], call_args[1]
        assert str(real_path).endswith("train.py")
        assert content == "# version 1\n"  # winner is idx 1


# ===========================================================================
# [v1.9 B3] Git toplevel verify (qwen P1-4)
# ===========================================================================


class TestGitToplevelVerify:
    """[v1.9 B3] _git_reset_hard verifies git rev-parse --show-toplevel
    matches project_root before resetting. Refuses if mismatch (symlink/
    junction to a different repo).
    """

    def test_git_reset_refuses_when_toplevel_mismatches(self, tmp_path):
        """[v1.10 / Phase B] _git_reset_hard is now imported from
        workflow_helpers. Patch _git to return a different toplevel path →
        reset_hard returns False + tracer.warning called."""
        from workflows.autoresearch_impl.nodes.decide import _git_reset_hard
        # rev-parse returns a DIFFERENT path → mismatch.
        different_path = str(tmp_path.parent / "other_repo")
        with patch("tools.git_ops.workflow_helpers._git",
                   return_value=(0, different_path + "\n", "")), \
             patch("workflows.autoresearch_impl.nodes.decide.tracer.warning") as mock_warn:
            result = _git_reset_hard(str(tmp_path), "tid")

        assert result is False
        assert mock_warn.called
        warn_msg = mock_warn.call_args[0][2]
        assert "toplevel mismatch" in warn_msg or "mismatch" in warn_msg


# ===========================================================================
# [v1.9 E1] Explicit NaN handling in _is_improvement (kimi #16)
# ===========================================================================


class TestIsImprovementNan:
    """[v1.9 E1] _is_improvement explicitly returns False for NaN metrics.
    Was: implicit (NaN comparisons are always False). Now documented via
    the `new != new` check (canonical NaN self-test).
    """

    def test_is_improvement_returns_false_for_nan_lower(self):
        """NaN with direction='lower' → False (not an improvement)."""
        from workflows.autoresearch_impl.nodes.decide import _is_improvement
        assert _is_improvement(float('nan'), 0.5, "lower") is False

    def test_is_improvement_returns_false_for_nan_higher(self):
        """NaN with direction='higher' → False (not an improvement)."""
        from workflows.autoresearch_impl.nodes.decide import _is_improvement
        assert _is_improvement(float('nan'), 0.5, "higher") is False

    def test_is_improvement_returns_false_for_nan_best(self):
        """NaN as the BEST value → False (can't improve on NaN)."""
        from workflows.autoresearch_impl.nodes.decide import _is_improvement
        assert _is_improvement(0.5, float('nan'), "lower") is False
