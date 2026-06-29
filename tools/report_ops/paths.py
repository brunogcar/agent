"""
report_ops/paths.py - Output path resolution with path guard.
"""

from __future__ import annotations

from pathlib import Path

from core.config import cfg
from core.path_guard import resolve_path


def report_out_dir(trace_id: str) -> Path:
    """
    Resolve and create the per-run output directory.
    Returns: workspace/reports/{trace_id}/
    """
    base = cfg.workspace_root / "reports"
    base.mkdir(parents=True, exist_ok=True)

    # Sanitize trace_id for filesystem safety
    safe_tid = "".join(c if c.isalnum() or c in "-_" else "_" for c in trace_id)
    out_dir = base / safe_tid
    out_dir.mkdir(parents=True, exist_ok=True)
    return out_dir


def report_manifest_path(trace_id: str) -> Path:
    return report_out_dir(trace_id) / "manifest.json"
