"""Node: evaluate — Extract metric from experiment output.

[v1.0] Greps the experiment output for `{metric_name}: <float>` (or `=` /
whitespace separator) and takes the LAST occurrence (training scripts often
print per-epoch metrics; we want the final value).

v1.2.1 (P1-2): Extracted _extract_metric to helpers.py (shared with setup.py).

If no metric is found (the experiment crashed, timed out, or printed in a
different format), the node sets current_metric to None and a sentinel
status so the decide node knows to discard the experiment.

Returns a PARTIAL state dict with `current_metric` and a status flag.

[v1.6] When `parallel_count > 1`, extracts N metrics from N outputs in
`experiment_outputs` (plural). Each output that yields no metric gets 0.0
(so `node_decide`'s `_is_improvement` check fails for it — direction=lower
with current_best=0 would falsely improve; but in practice current_best is
the baseline metric which is always > 0 for real metrics). The N metrics
are stored in `current_metrics` (plural); the first is mirrored to
`current_metric` (singular) for v1.5 backward compat. When
`parallel_count == 1`, the v1.5 single-extraction path runs unchanged.
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

    [v1.6] When `parallel_count > 1`, extracts N metrics from N outputs.
    Per-output failures (no metric found) yield 0.0 for that slot — the
    downstream `node_decide` parallel path skips experiments whose proposal
    has `status="failed"` (set by modify) OR whose metric didn't improve.
    """
    tid = state.get("trace_id", "")
    metric_name = state.get("metric_name", "") or cfg.autoresearch_metric_name
    parallel_count = int(state.get("parallel_count", 1) or 1)

    # ── [v1.6] Parallel path: extract N metrics from N outputs ─────────────
    if parallel_count > 1:
        outputs = state.get("experiment_outputs", []) or []
        metrics: list[float] = []
        for i, output in enumerate(outputs):
            m = _extract_metric(output, metric_name)
            if m is None:
                tracer.warning(
                    tid, "evaluate",
                    f"parallel experiment {i}: metric '{metric_name}' not found "
                    f"({len(output)} chars captured)",
                )
                metrics.append(0.0)
            else:
                tracer.step(tid, "evaluate", f"parallel experiment {i}: {metric_name}={m}")
                metrics.append(m)

        return {
            "current_metrics": metrics,
            # Mirror the first metric for v1.5 backward compat (singular
            # field is used by node_decide when parallel_count==1).
            "current_metric": metrics[0] if metrics else 0.0,
            "status": "running",
            "error": "",
        }

    # ── v1.5 single-extraction path (unchanged) ────────────────────────────
    output = state.get("experiment_output", "")

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
