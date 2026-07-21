"""tests/workflows/autoresearch/test_cancellation.py

[v1.10 / Phase B] Cancellation tests for autoresearch nodes.

4 tests, one per node:
  - test_propose_cancelled — node_propose returns {status: failed, errors: [...]}
    before the LLM call.
  - test_run_experiment_cancelled — node_run_experiment returns {status: failed}
    before spawning subprocesses.
  - test_decide_cancelled — node_decide returns {status: failed} before the
    git commit (and cleans up the parallel temp dir).
  - test_reflect_cancelled — node_reflect returns {} (no-op) before the
    reflection LLM call.

Each test patches `workflows.autoresearch_impl.nodes.<node>._is_cancelled` to
return True, then asserts the early-exit return shape. The LLM call / git
commit / subprocess is NOT invoked (verified by patching + asserting not
called).
"""
from __future__ import annotations

from unittest.mock import patch

import pytest


# ---------------------------------------------------------------------------
# node_propose cancellation
# ---------------------------------------------------------------------------


def test_propose_cancelled(ar_state):
    """node_propose returns {status: failed, errors: [Workflow cancelled]}
    when cancelled — LLM call NOT made."""
    from workflows.autoresearch_impl.nodes.propose import node_propose
    state = dict(ar_state)
    state["current_best"] = 0.5
    state["experiment_history"] = []

    with patch("workflows.autoresearch_impl.nodes.propose._is_cancelled",
               return_value=True), \
         patch("workflows.autoresearch_impl.nodes.propose._call_planner") as m_call:
        result = node_propose(state)

    assert result["status"] == "failed"
    assert "Workflow cancelled" in result.get("errors", [])
    # _call_planner must NOT be called — cancellation fired before the LLM call.
    m_call.assert_not_called()


# ---------------------------------------------------------------------------
# node_run_experiment cancellation
# ---------------------------------------------------------------------------


def test_run_experiment_cancelled(ar_state):
    """node_run_experiment returns {status: failed, errors: [...]} when
    cancelled — subprocess NOT spawned."""
    from workflows.autoresearch_impl.nodes.run_experiment import node_run_experiment
    state = dict(ar_state)

    with patch("workflows.autoresearch_impl.nodes.run_experiment._is_cancelled",
               return_value=True), \
         patch("workflows.autoresearch_impl.nodes.run_experiment._run_subprocess") as m_sub:
        result = node_run_experiment(state)

    assert result["status"] == "failed"
    assert "Workflow cancelled" in result.get("errors", [])
    # Subprocess runner must NOT be called.
    m_sub.assert_not_called()


# ---------------------------------------------------------------------------
# node_decide cancellation
# ---------------------------------------------------------------------------


def test_decide_cancelled(ar_state, tmp_path):
    """node_decide returns {status: failed, errors: [...]} when cancelled —
    git commit NOT made. Parallel temp dir is still cleaned up."""
    from workflows.autoresearch_impl.nodes.decide import node_decide
    state = dict(ar_state)
    state.update({
        "current_best": 0.5, "current_metric": 0.4,
        "metric_direction": "lower",
        "current_experiment": {"iteration": 1, "description": "good"},
        "project_root": str(tmp_path),
    })

    with patch("workflows.autoresearch_impl.nodes.decide._is_cancelled",
               return_value=True), \
         patch("workflows.autoresearch_impl.nodes.decide._git_commit") as m_commit:
        result = node_decide(state)

    assert result["status"] == "failed"
    assert "Workflow cancelled" in result.get("errors", [])
    # _git_commit must NOT be called — cancellation fired before the commit.
    m_commit.assert_not_called()


# ---------------------------------------------------------------------------
# node_reflect cancellation
# ---------------------------------------------------------------------------


def test_reflect_cancelled(ar_state):
    """node_reflect returns {} (no-op) when cancelled — LLM call NOT made."""
    from workflows.autoresearch_impl.nodes.reflect import node_reflect
    state = dict(ar_state)
    # Reflect only fires on multiples of `interval` — set iteration_count to
    # a multiple so the node WOULD normally call _call_planner. The
    # cancellation check fires BEFORE the interval check, so this doesn't
    # matter, but it makes the test more robust.
    state["iteration_count"] = 5  # default interval is 5 → would fire

    with patch("workflows.autoresearch_impl.nodes.reflect._is_cancelled",
               return_value=True), \
         patch("workflows.autoresearch_impl.nodes.reflect._call_planner") as m_call:
        result = node_reflect(state)

    assert result == {}  # no-op
    # _call_planner must NOT be called.
    m_call.assert_not_called()
