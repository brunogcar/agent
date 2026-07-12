"""Routing functions for the autoresearch workflow.

[v1.0] Two routers:
  route_after_evaluate — always proceeds to "log" (we log every experiment,
      whether it improved the metric or not, so the ledger is complete).
  route_after_decide   — always proceeds to "propose" (the experiment loop
      runs indefinitely until a human interrupts the process).
"""
from __future__ import annotations

from workflows.autoresearch_impl.state import AutoresearchState


def route_after_evaluate(state: AutoresearchState) -> str:
    """After evaluate: always log (we want a complete ledger, including failures).

    The decision to keep or discard happens AFTER logging, in the decide node.
    This ensures results.tsv always reflects every experiment that was run —
    even ones whose metric was worse than the current best.
    """
    # If evaluate failed (no metric extracted), we still log the run with a
    # sentinel status — operators want to see the failed experiment in the
    # ledger so they can debug what the LLM proposed.
    return "log"


def route_after_decide(state: AutoresearchState) -> str:
    """After decide: always loop back to propose.

    The autoresearch loop is evolutionary and runs indefinitely. A human
    interrupts the process when satisfied with the current_best (or when the
    LLM has stopped proposing productive changes). LangGraph's recursion_limit
    should be raised by the caller (or via the dispatcher) so the loop can
    run for the desired number of iterations.
    """
    return "propose"
