"""Per-role metrics collection for the agent tool.

Lightweight in-memory tracking of call volume, success/failure rates,
elapsed time, token consumption, and parse failures. Metrics are
aggregated per role and can be queried via the meta-role agent(role="metrics").

This module is stateful at the process level. Tests must call _clear_metrics()
in setup_method to avoid cross-test contamination.
"""
from __future__ import annotations

import time as _time

# Module-level metrics storage — keyed by role name.
# Each entry is a dict with call counters and aggregates.
_ROLE_METRICS: dict[str, dict] = {}


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


def _clear_metrics() -> None:
    """Clear all metrics. Primarily for testing isolation."""
    _ROLE_METRICS.clear()
