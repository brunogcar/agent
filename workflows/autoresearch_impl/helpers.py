"""Shared helpers for the autoresearch workflow.

v1.2.1 (P1-2): Extracted _extract_metric from setup.py + evaluate.py.
Both had identical regex logic — now a single source of truth.

v1.3 (P2-1): Extracted run_target_subprocess from setup.py + run_experiment.py.
Both had nearly-identical subprocess-run-with-timeout logic — now a single
source of truth. The two originals diverged in subtle ways (one caught
FileNotFoundError, the other didn't; one used `e.stdout or ""` patterns
differently). Consolidating eliminates that drift.

v1.11 (A7): run_target_subprocess now uses Popen + process-group isolation
so timeout kills the ENTIRE process tree (was: subprocess.run killed only
the immediate child — PyTorch DataLoader workers, multiprocessing, CUDA
contexts survived as orphans, contending for GPU/CPU on the next experiment).
"""
from __future__ import annotations

import os
import re
import signal
import subprocess
import sys
import time
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
    Time-boxed via subprocess timeout. On timeout, partial output is returned
    with a sentinel. On FileNotFoundError, a clear error is returned.

    [v1.11 A7] Process-group isolation — on timeout, the ENTIRE process tree
    is killed (was: only the immediate child). Pre-v1.11, subprocess.run's
    timeout killed only the top-level `python` process; if the target_file
    spawned workers (PyTorch DataLoader, multiprocessing, CUDA contexts),
    those survived as orphans, contending for GPU/CPU on the next experiment.
    POSIX: start_new_session=True (setsid) + os.killpg(SIGTERM then SIGKILL).
    Windows: CREATE_NEW_PROCESS_GROUP + taskkill /T /F /PID.
    """
    cmd = [sys.executable, target_file]
    # [v1.11 A7] Process-group isolation so timeout kills the whole tree.
    kwargs = {
        "stdout": subprocess.PIPE,
        "stderr": subprocess.PIPE,
        "text": True,
        "cwd": project_root or None,
    }
    if os.name == "posix":
        kwargs["start_new_session"] = True  # setsid — new process group
    elif os.name == "nt":
        kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP

    try:
        proc = subprocess.Popen(cmd, **kwargs)
    except FileNotFoundError:
        return f"[autoresearch] target_file not found: {target_file}\n"

    try:
        stdout, stderr = proc.communicate(timeout=time_budget)
        return (stdout or "") + (stderr or "")
    except subprocess.TimeoutExpired:
        # [v1.11 A7] Kill the ENTIRE process group, not just the top process.
        _kill_process_tree(proc)
        # Collect whatever output was captured before the kill (best-effort).
        try:
            stdout, stderr = proc.communicate(timeout=5)
        except Exception:
            stdout, stderr = "", ""
        out = (stdout or "") + (stderr or "")
        out += f"\n[autoresearch] experiment timed out after {time_budget}s\n"
        return out
    except Exception as e:
        _kill_process_tree(proc)
        return f"[autoresearch] experiment crashed: {type(e).__name__}: {e}\n"


def _kill_process_tree(proc: subprocess.Popen) -> None:
    """[v1.11 A7] Kill a process + all its descendants.

    POSIX: os.killpg(SIGTERM then SIGKILL after 0.5s grace).
    Windows: taskkill /T /F /PID (tree kill, force).
    Best-effort — ignores errors (process may already be dead).
    """
    try:
        if os.name == "posix":
            try:
                pgid = os.getpgid(proc.pid)
                os.killpg(pgid, signal.SIGTERM)
                time.sleep(0.5)  # grace period for graceful shutdown
                os.killpg(pgid, signal.SIGKILL)  # force kill any survivors
            except (ProcessLookupError, OSError):
                pass  # already dead
        elif os.name == "nt":
            subprocess.run(
                ["taskkill", "/T", "/F", "/PID", str(proc.pid)],
                capture_output=True, timeout=10,
            )
        else:
            # Unknown OS — fall back to plain terminate.
            proc.terminate()
    except Exception:
        pass
    # Final fallback — ensure the top process is dead.
    try:
        proc.kill()
    except Exception:
        pass
