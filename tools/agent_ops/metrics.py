"""Per-role metrics collection for the agent tool.

Lightweight in-memory tracking of call volume, success/failure rates,
elapsed time, token consumption, and parse failures. Metrics are
aggregated per role and can be queried via the meta-role agent(role="metrics").

[Bug #20] Optional JSONL persistence: metrics are appended to
.agent_metrics.jsonl in the workspace root on each call, so they survive
process restarts. The in-memory dict remains the primary store for fast
reads; the JSONL is an append-only audit log for long-term analysis.
Set AGENT_METRICS_PERSIST=0 in .env to disable (defaults to enabled).

[Bug #24] Aggregation: _get_aggregate_metrics() returns total calls,
overall success rate, and average latency across all roles.

This module is stateful at the process level. Tests must call _clear_metrics()
in setup_method to avoid cross-test contamination.
"""
from __future__ import annotations

import json as _json
import os
import time as _time
from pathlib import Path as _Path

# Module-level metrics storage — keyed by role name.
# Each entry is a dict with call counters and aggregates.
_ROLE_METRICS: dict[str, dict] = {}

# [Bug #20] Persistence path — lazy-initialized to avoid import-time cfg dep.
_METRICS_LOG_PATH: _Path | None = None
_PERSIST_ENABLED: bool | None = None


def _get_metrics_log_path() -> _Path | None:
    """Return the JSONL log path for metrics, or None if persistence disabled."""
    global _METRICS_LOG_PATH, _PERSIST_ENABLED
    if _PERSIST_ENABLED is False:
        return None
    if _METRICS_LOG_PATH is not None:
        return _METRICS_LOG_PATH
    try:
        from core.config import cfg
        _PERSIST_ENABLED = os.getenv("AGENT_METRICS_PERSIST", "1") != "0"
        if not _PERSIST_ENABLED:
            return None
        _METRICS_LOG_PATH = _Path(cfg.workspace_root) / ".agent_metrics.jsonl"
    except Exception:
        _PERSIST_ENABLED = False
        return None
    return _METRICS_LOG_PATH


def _persist_metric(role: str, status: str, elapsed: float, tokens: int, parse_failed: bool) -> None:
    """Append a single metric event to the JSONL log (best-effort)."""
    path = _get_metrics_log_path()
    if path is None:
        return
    try:
        entry = {
            "ts": _time.time(),
            "role": role,
            "status": status,
            "elapsed": elapsed,
            "tokens": tokens,
            "parse_failed": parse_failed,
        }
        with open(path, "a", encoding="utf-8") as f:
            f.write(_json.dumps(entry) + "\n")
    except Exception:
        pass  # Non-fatal: persistence is best-effort, never block the agent


def _record_metric(
    role: str,
    status: str,
    elapsed: float,
    tokens: int,
    parse_failed: bool = False,
) -> None:
    """Record a lightweight metric for the given role.

    Metrics are stored in memory and can be queried via agent(role="metrics").
    This is prerequisite infrastructure for self-improving prompts.

    Args:
        role: The agent role that was invoked (e.g. "classify", "plan").
        status: "success" or "error" — outcome of the LLM call.
        elapsed: Wall-clock time in seconds for the call (or aggregate for
            fallback+escalation chains).
        tokens: Total token consumption from result.usage["total"].
        parse_failed: True if JSON parsing failed after all fallback attempts.
    """
    if role not in _ROLE_METRICS:
        _ROLE_METRICS[role] = {
            "calls": 0,
            "successes": 0,
            "failures": 0,
            "total_elapsed": 0.0,
            "total_tokens": 0,
            "parse_failures": 0,
            "last_call": None,
        }
    m = _ROLE_METRICS[role]
    m["calls"] += 1
    m["last_call"] = _time.time()
    if status == "success":
        m["successes"] += 1
    else:
        m["failures"] += 1
    m["total_elapsed"] += elapsed
    m["total_tokens"] += tokens
    if parse_failed:
        m["parse_failures"] += 1

    # [Bug #20] Persist to JSONL (best-effort, never blocks)
    _persist_metric(role, status, elapsed, tokens, parse_failed)


def _get_metrics(role: str | None = None) -> dict:
    """Return metrics for a specific role or all roles.

    Args:
        role: Role name to filter by, or None for all roles.

    Returns:
        If role is given: a shallow copy of the metrics dict for that role,
            or {} if none.
        If role is None: a shallow copy of the full metrics mapping.
    """
    if role:
        return _ROLE_METRICS.get(role, {}).copy()
    return dict(_ROLE_METRICS)


def _get_aggregate_metrics() -> dict:
    """[Bug #24] Return aggregate stats across all roles.

    Returns:
        Dict with:
            total_calls: int — sum of all role calls
            total_successes: int
            total_failures: int
            overall_success_rate: float (0.0-1.0)
            avg_latency: float — average elapsed seconds per call
            total_tokens: int
            total_parse_failures: int
            roles_tracked: int — number of distinct roles with metrics
    """
    total_calls = sum(m["calls"] for m in _ROLE_METRICS.values())
    total_successes = sum(m["successes"] for m in _ROLE_METRICS.values())
    total_failures = sum(m["failures"] for m in _ROLE_METRICS.values())
    total_elapsed = sum(m["total_elapsed"] for m in _ROLE_METRICS.values())
    total_tokens = sum(m["total_tokens"] for m in _ROLE_METRICS.values())
    total_parse_failures = sum(m["parse_failures"] for m in _ROLE_METRICS.values())
    return {
        "total_calls": total_calls,
        "total_successes": total_successes,
        "total_failures": total_failures,
        "overall_success_rate": (total_successes / total_calls) if total_calls else 0.0,
        "avg_latency": (total_elapsed / total_calls) if total_calls else 0.0,
        "total_tokens": total_tokens,
        "total_parse_failures": total_parse_failures,
        "roles_tracked": len(_ROLE_METRICS),
    }


def _clear_metrics() -> None:
    """Clear all metrics. Primarily for testing isolation."""
    _ROLE_METRICS.clear()
    # [Bug #20] Also reset persistence cache so tests get a clean path
    global _METRICS_LOG_PATH, _PERSIST_ENABLED
    _METRICS_LOG_PATH = None
    _PERSIST_ENABLED = None
