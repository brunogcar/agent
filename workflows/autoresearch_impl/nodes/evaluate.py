"""Node: evaluate — Extract metric from experiment output.

[v1.0] Greps the experiment output for `{metric_name}: <float>` (or `=` /
whitespace separator) and takes the LAST occurrence (training scripts often
print per-epoch metrics; we want the final value).

v1.2.1 (P1-2): Extracted _extract_metric to helpers.py (shared with setup.py).

If no metric is found (the experiment crashed, timed out, or printed in a
different format), the node sets current_metric to None and a sentinel
status so the decide node knows to discard the experiment.

Returns a PARTIAL state dict with `current_metric` and a status flag.
"""
from __future__ import annotations

from typing import Optional

from core.config import cfg
from core.tracer import tracer
from workflows.autoresearch_impl.state import AutoresearchState
from workflows.autoresearch_impl.helpers import extract_metric as _extract_metric


def node_evaluate(state: AutoresearchState) -> dict:
    """Extract the metric from the last experiment's output.

    Returns a partial state dict with `current_metric` (float or 0.0 on
    failure) and `status` ("running" on success, "failed" if metric missing).
    """
    tid = state.get("trace_id", "")
    output = state.get("experiment_output", "")
    metric_name = state.get("metric_name", "") or cfg.autoresearch_metric_name

    if state.get("status") == "failed":
        # Propagate the prior failure (e.g. modify failed) — decide will discard.
        tracer.step(tid, "evaluate", "skipping — prior node failed")
        return {"current_metric": 0.0}

    metric = _extract_metric(output, metric_name)
    if metric is None:
        tracer.warning(
            tid, "evaluate",
            f"metric '{metric_name}' not found in experiment output "
            f"({len(output)} chars captured)",
        )
        return {
            "current_metric": 0.0,
            "status": "failed",
            "error": f"metric '{metric_name}' not found in experiment output",
        }

    tracer.step(tid, "evaluate", f"{metric_name}={metric}")
    return {
        "current_metric": metric,
        "status": "running",
        "error": "",
    }
