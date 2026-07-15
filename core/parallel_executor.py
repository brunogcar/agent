"""core/parallel_executor.py — Backwards-compat shim.

All parallel execution logic moved to tools.parallel_ops.executor in v1.0.
This file remains as a thin re-export so existing imports
(`from core.parallel_executor import dispatch_parallel, PARALLEL_SAFE,
_parallel_depth, _safe_run`) continue to work without code changes.

NEW CODE should import directly from tools.parallel_ops.executor / .tool_map:
    from tools.parallel_ops.executor import dispatch_run, dispatch_race, dispatch_pipeline
    from tools.parallel_ops.tool_map import PARALLEL_SAFE, _TOOL_MAP, _get_tool_fn

`dispatch_parallel` here is an alias for `dispatch_run` (the v1.0 name).
"""
from __future__ import annotations

# Re-export everything callers may have imported from this module.
from tools.parallel_ops.executor import (
    dispatch_run as dispatch_parallel,
    dispatch_run,
    dispatch_race,
    dispatch_pipeline,
    _parallel_depth,
    _safe_run,
)
from tools.parallel_ops.tool_map import PARALLEL_SAFE, _TOOL_MAP, _get_tool_fn

__all__ = [
    "dispatch_parallel",  # legacy name (alias for dispatch_run)
    "dispatch_run",       # v1.0 name
    "dispatch_race",
    "dispatch_pipeline",
    "PARALLEL_SAFE",
    "_TOOL_MAP",
    "_get_tool_fn",
    "_parallel_depth",
    "_safe_run",
]
