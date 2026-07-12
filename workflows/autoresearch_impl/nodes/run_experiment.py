"""Node: run_experiment — Execute the target_file as a time-boxed subprocess.

[v1.0] Runs the (now-modified) target_file as a subprocess, captures stdout
+ stderr, and stores the combined output in state.experiment_output.

The subprocess is time-boxed via state.time_budget (default 300s). If the
budget is exceeded, the subprocess is killed and a sentinel message is
appended to the output so the evaluate node can detect the timeout.

Returns a PARTIAL state dict with `experiment_output` and a status flag.
"""
from __future__ import annotations

import subprocess
import sys

from core.config import cfg
from core.tracer import tracer
from workflows.autoresearch_impl.state import AutoresearchState


def _run_subprocess(target_file: str, project_root: str, time_budget: int) -> str:
    """Run target_file as `python <target_file>` in project_root.

    Time-boxed via subprocess.run(timeout=...). On timeout, the partial
    output captured so far is returned with a sentinel appended so the
    evaluate node can detect the timeout condition.

    Returns combined stdout+stderr as a string.
    """
    cmd = [sys.executable, target_file]
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=time_budget,
            cwd=project_root or None,
        )
        return (result.stdout or "") + (result.stderr or "")
    except subprocess.TimeoutExpired as e:
        # TimeoutExpired.stdout/stderr may be bytes or str depending on the
        # `text=` flag — we set text=True so they're strings (or None).
        out = ""
        if isinstance(e.stdout, str):
            out += e.stdout or ""
        if isinstance(e.stderr, str):
            out += e.stderr or ""
        out += f"\n[autoresearch] experiment timed out after {time_budget}s\n"
        return out
    except FileNotFoundError as e:
        return f"[autoresearch] target_file not found: {e}\n"
    except Exception as e:
        return f"[autoresearch] experiment crashed: {type(e).__name__}: {e}\n"


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
