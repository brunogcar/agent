"""Node: run_experiment — Execute the target_file as a time-boxed subprocess.

[v1.0] Runs the (now-modified) target_file as a subprocess, captures stdout
+ stderr, and stores the combined output in state.experiment_output.

The subprocess is time-boxed via state.time_budget (default 300s). If the
budget is exceeded, the subprocess is killed and a sentinel message is
appended to the output so the evaluate node can detect the timeout.

Returns a PARTIAL state dict with `experiment_output` and a status flag.

[v1.3 P2-1] `_run_subprocess` removed — replaced with the shared
`workflows.autoresearch_impl.helpers.run_target_subprocess`. The two
originals (in setup.py + run_experiment.py) had drifted in subtle ways
(one caught FileNotFoundError, the other didn't); consolidating eliminates
that drift.
"""
from __future__ import annotations

import subprocess
import sys

from core.config import cfg
from core.tracer import tracer
from workflows.autoresearch_impl.state import AutoresearchState
from workflows.autoresearch_impl.helpers import run_target_subprocess as _run_subprocess

# v1.3 (P2-1): _run_subprocess now imported from helpers.py (was a local copy).


def node_run_experiment(state: AutoresearchState) -> dict:
    """Run the modified target_file as a subprocess.

    Returns a partial state dict with `experiment_output`.
    """
    tid = state.get("trace_id", "")
    target_file = state.get("target_file", "") or cfg.autoresearch_target_file
    project_root = state.get("project_root", "")
    time_budget = state.get("time_budget", cfg.autoresearch_time_budget)

    # If modify failed, skip the run — decide will discard.
    if state.get("status") == "failed":
        tracer.step(tid, "run_experiment", "skipping run — prior node failed")
        return {"experiment_output": state.get("experiment_output", "")}

    tracer.step(
        tid, "run_experiment",
        f"running {target_file} (budget={time_budget}s) @ {project_root or 'cwd'}",
    )
    output = _run_subprocess(target_file, project_root, time_budget)

    # Truncate very large outputs to prevent state bloat. 50KB is enough for
    # the evaluate node to find the metric (usually printed at the end) while
    # keeping the trace log manageable.
    if len(output) > 50_000:
        output = output[-50_000:]
        tracer.warning(tid, "run_experiment", f"output truncated to last 50KB (was larger)")

    return {
        "experiment_output": output,
        "status": "running",
        "error": "",
    }
