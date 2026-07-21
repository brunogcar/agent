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

[v1.8 N10] The single-extraction path now checks `state["pre_extracted_metric"]`
FIRST. `node_run_experiment` extracts the metric from the FULL output BEFORE
truncating to 50KB and stores it there. When set (not None), `node_evaluate`
trusts it and skips re-extracting from the (possibly truncated)
`experiment_output`. This prevents false negatives when the metric was
printed early and the script produced lots of output after, pushing the
metric out of the 50KB tail. When None (no metric in the full output),
falls through to the existing extraction-from-output path (which will also
yield None → status="failed").

[v1.9-V2 / mistral #10] The parallel path now ALSO checks
`state["pre_extracted_metrics"][i]` FIRST for each output i — mirrors the
single-path pre-extract (v1.8 N10). A verbose parallel experiment >50KB
can lose its metric in the truncation tail, just like single mode. When set
(not None), `node_evaluate` trusts it and skips re-extracting from the
(possibly truncated) `experiment_outputs[i]`. When None or when `i` is past
the end of the list (defensive — should not happen since run_experiment
always populates N entries), falls through to the existing extraction-from-
output path.
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

    [v1.9-V2 / mistral #10] Parallel path checks `pre_extracted_metrics[i]`
    FIRST for each output i (mirrors single-path v1.8 N10). Falls through to
    re-extracting from the (possibly truncated) output when the pre-extracted
    value is None or missing.
    """
    tid = state.get("trace_id", "")
    metric_name = state.get("metric_name", "") or cfg.autoresearch_metric_name
    parallel_count = int(state.get("parallel_count", 1) or 1)

    # ── [v1.6] Parallel path: extract N metrics from N outputs ─────────────
    if parallel_count > 1:
        outputs = state.get("experiment_outputs", []) or []
        # [v1.9-V2 / mistral #10] Pre-extracted per-output metrics from the
        # FULL outputs (before truncation). node_run_experiment populates this
        # list in parallel mode — mirrors the single-path pre_extracted_metric.
        pre_metrics = state.get("pre_extracted_metrics", []) or []
        metrics: list[float] = []
        for i, output in enumerate(outputs):
            # [v1.9-V2 / mistral #10] Check pre_extracted_metrics[i] FIRST.
            # When set (not None), trust it + skip re-extracting from the
            # (possibly truncated) output. Defensive: also bounds-check i
            # so a malformed state dict (pre_metrics shorter than outputs)
            # doesn't IndexError.
            pre_m = pre_metrics[i] if i < len(pre_metrics) else None
            if pre_m is not None:
                tracer.step(
                    tid, "evaluate",
                    f"parallel experiment {i}: {metric_name}={pre_m} "
                    f"(pre-extracted from full output)",
                )
                metrics.append(pre_m)
                continue
            # Fall back to extracting from the (possibly truncated) output.
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

    # [v1.8 N10] Use pre-extracted metric if available — prevents truncation
    # false negatives. node_run_experiment extracts the metric from the FULL
    # output BEFORE truncating to 50KB and stores it in `pre_extracted_metric`.
    # When set (not None), we trust it and skip re-extracting from the
    # (possibly truncated) `experiment_output`. When None (no metric in the
    # full output), fall through to the extraction below — which will also
    # yield None and produce the same "metric not found" failure path.
    pre_metric = state.get("pre_extracted_metric")
    if pre_metric is not None:
        tracer.step(
            tid, "evaluate",
            f"{metric_name}={pre_metric} (pre-extracted from full output)",
        )
        return {
            "current_metric": pre_metric,
            "status": "running",
            "error": "",
        }

    # Fall back to extracting from (possibly truncated) output.
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
