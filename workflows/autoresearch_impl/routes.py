"""Routing functions for the autoresearch workflow.

[v1.0] Three routers (v1.2.1 had two unconditional routes; v1.3 collapses
both into direct edges — see graph.py). Only one router remains:

  route_after_setup    — proceeds to "propose" on success, "end" on failure
      (v1.2.1: was a linear edge that let setup failures spin the loop).

[v1.3 P2-5] route_after_evaluate and route_after_decide have been DELETED.
Both were single-destination "fake" conditional edges (always returned the
same value). They are now direct `add_edge(...)` calls in graph.py:
  - evaluate → decide
  - decide   → log
This matches the new evaluate → decide → log → propose loop order (v1.3 P0-1).
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
