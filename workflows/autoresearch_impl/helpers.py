"""Shared helpers for the autoresearch workflow.

v1.2.1 (P1-2): Extracted _extract_metric from setup.py + evaluate.py.
Both had identical regex logic — now a single source of truth.

v1.3 (P2-1): Extracted run_target_subprocess from setup.py + run_experiment.py.
Both had nearly-identical subprocess-run-with-timeout logic — now a single
source of truth. The two originals diverged in subtle ways (one caught
FileNotFoundError, the other didn't; one used `e.stdout or ""` patterns
differently). Consolidating eliminates that drift.
"""
from __future__ import annotations

import re
import subprocess
import sys
from typing import Optional


def extract_metric(output: str, metric_name: str) -> Optional[float]:
    """Extract the LAST occurrence of `{metric_name}: <float>` from output.

    Accepts `:`, `=`, or whitespace as the separator before the value.
    Returns None if no match is found or the matched value can't be parsed.

    Used by:
      - node_setup (baseline metric extraction)
      - node_evaluate (per-experiment metric extraction)
    """
    if not output or not metric_name:
        return None
    # Escape the metric name to handle special characters (e.g. "val/loss").
    # Accept `:`, `=`, or whitespace as separator before the value.
    pattern = rf"{re.escape(metric_name)}\s*[:=]\s*([+-]?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?)"
    matches = re.findall(pattern, output)
    if not matches:
        return None
    try:
        return float(matches[-1])
    except (ValueError, IndexError):
        return None


def run_target_subprocess(target_file: str, project_root: str, time_budget: int) -> str:
    """Run target_file as `python <target_file>` in project_root.

    [v1.3 P2-1] Extracted from setup.py + run_experiment.py (was duplicated).
    Time-boxed via subprocess.run(timeout=...). On timeout, partial output
    is returned with a sentinel. On FileNotFoundError, a clear error is returned.
    """
    cmd = [sys.executable, target_file]
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True,
            timeout=time_budget, cwd=project_root or None,
        )
        return (result.stdout or "") + (result.stderr or "")
    except subprocess.TimeoutExpired as e:
        out = ""
        if isinstance(e.stdout, str):
            out += e.stdout or ""
        if isinstance(e.stderr, str):
            out += e.stderr or ""
        out += f"\n[autoresearch] experiment timed out after {time_budget}s\n"
        return out
    except FileNotFoundError:
        return f"[autoresearch] target_file not found: {target_file}\n"
    except Exception as e:
        return f"[autoresearch] experiment crashed: {type(e).__name__}: {e}\n"
