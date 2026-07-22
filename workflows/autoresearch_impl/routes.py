"""Routing functions for the autoresearch workflow.

[v1.0] Three routers (v1.2.1 had two unconditional routes; v1.3 collapses
both into direct edges — see graph.py). Only one router remained until v1.4:

  route_after_setup    — proceeds to "propose" on success, "end" on failure
      (v1.2.1: was a linear edge that let setup failures spin the loop).

[v1.3 P2-5] route_after_evaluate and route_after_decide have been DELETED.
Both were single-destination "fake" conditional edges (always returned the
same value). They became direct `add_edge(...)` calls in graph.py:
  - evaluate → decide
  - decide   → log
This matches the v1.3 P0-1 evaluate → decide → log → propose loop order.

[v1.4] route_after_log added — the log → propose back-edge is now conditional
(instead of the v1.3 direct edge). It checks 3 stopping conditions in order:
  1. max_iterations reached (0 = unlimited, legacy v1.3 behavior).
  2. Convergence: last N experiments all discarded (no improvement).
  3. Stuck: last N experiments all have metric within ε of current_best.
If any condition holds, routes to END; otherwise continues to "propose".
"""
from __future__ import annotations

from workflows.autoresearch_impl.state import AutoresearchState


def route_after_setup(state: AutoresearchState) -> str:
    """After setup: proceed to propose on success, END on failure.

    v1.2.1 (P1-1): If setup fails (baseline metric not extracted), the
    workflow used to spin infinitely — propose (LLM call = token cost) →
    skip → skip → skip → discard → log → propose → ... Now routes to END.
    """
    if state.get("status") == "failed":
        return "end"
    return "propose"


def route_after_log(state: AutoresearchState) -> str:
    """[v1.4] After log: check stopping conditions before looping back to propose.

    Returns "propose" to continue the loop, or "end" to stop.

    Stopping conditions (checked in order):
    1. max_iterations reached — caller-set hard cap (0 = unlimited).
       [v1.11 A9] Counts EXPERIMENTS (not iterations). In parallel mode
       (parallel_count=N), experiment_count jumps by N per iteration, so
       max_iterations=10 with parallel_count=4 trips after ~2.5 iterations.
       Scale max_iterations by parallel_count if you want iteration-level
       control.
    2. Convergence: last N experiments all discarded (no improvement).
       N = convergence_window (default 10). Detects "nothing is working".
       [v1.11 A9] Counts EXPERIMENTS (not iterations). In parallel mode,
       each iteration appends parallel_count entries to experiment_history,
       so convergence_window=10 with parallel_count=4 spans ~2.5 iterations.
       Scale convergence_window by parallel_count if you want iteration-level
       control (e.g. convergence_window=40 for "10 iterations of all-discards
       at parallel_count=4"). The per-experiment semantics are arguably more
       honest (10 bad experiments is a stronger signal than 10 bad
       iterations), so this is a documentation clarification, not a code fix.
    3. Stuck: last N experiments all have metric within ε of current_best.
       ε = convergence_epsilon (default 0.001). Detects "metric plateau".
       [v1.11 A9] Same experiment-vs-iteration caveat as condition 2.

    All three are OFF by default (max_iterations=0, window large, ε small),
    so v1.4 preserves v1.3's "loop forever" behavior unless a caller opts
    in via run_workflow(max_iterations=...) or env vars.

    Safety: each condition requires `len(history) >= window` (so the first
    few iterations never trigger a false-positive stop). max_iterations=0
    means unlimited (skip condition 1).
    """
    experiment_count = state.get("experiment_count", 0)
    max_iter = state.get("max_iterations", 0)
    window = state.get("convergence_window", 10)
    epsilon = state.get("convergence_epsilon", 0.001)
    history = state.get("experiment_history", []) or []
    current_best = state.get("current_best", 0.0)

    # 1. Max iterations — explicit hard cap. 0 = unlimited (legacy v1.3).
    if max_iter > 0 and experiment_count >= max_iter:
        return "end"

    # 2. Convergence: last N all discarded (no improvement in N tries).
    #    Requires len(history) >= window so the first few iterations don't
    #    false-positive on an empty / short history.
    if len(history) >= window:
        recent = history[-window:]
        if all(h.get("status") == "discard" for h in recent):
            return "end"

    # 3. Stuck: last N all have metric within ε of current_best (plateau).
    #    Catches "the LLM keeps proposing changes that don't move the needle".
    if len(history) >= window:
        recent = history[-window:]
        metrics = [h.get("metric", 0.0) for h in recent]
        if all(abs(m - current_best) < epsilon for m in metrics):
            return "end"

    return "propose"
