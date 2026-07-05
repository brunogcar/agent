"""Parse warning logging for data-driven prompt tuning.

When a prompt-only JSON role (route, plan, code, review) fails to produce
valid JSON after all extraction and escalation attempts, a parse warning is
logged. The rolling log (max 50 entries) enables analysis of which roles
are degrading over time, so their system prompts can be tightened.

This module is stateful at the process level. Tests must call
_clear_parse_warnings() in setup_method to avoid cross-test contamination.
"""
from __future__ import annotations

import time as _time

# Module-level rolling log — newest entries appended at the end.
# Trimmed to _PARSE_WARNING_LOG_MAX via pop(0) when exceeded.
_PARSE_WARNING_LOG: list[dict] = []
_PARSE_WARNING_LOG_MAX = 50


def _log_parse_warning(role: str, warning: str, text_preview: str) -> None:
    """Log a parse warning for later analysis of prompt degradation.

    This enables data-driven prompt tuning: if a role's parse_warning rate
    spikes, its system prompt likely needs tightening.

    Args:
        role: The agent role that produced unparseable JSON.
        warning: The human-readable parse warning message.
        text_preview: First 200 chars of the raw LLM response for debugging.
    """
    _PARSE_WARNING_LOG.append({
        "timestamp": _time.time(),
        "role": role,
        "warning": warning,
        "text_preview": text_preview[:200],
    })
    # Trim to max size — pop(0) is O(n) but max 50 entries makes it trivial.
    while len(_PARSE_WARNING_LOG) > _PARSE_WARNING_LOG_MAX:
        _PARSE_WARNING_LOG.pop(0)


def _get_parse_warnings(role: str | None = None) -> list[dict]:
    """Return recent parse warnings, optionally filtered by role.

    Args:
        role: Role name to filter by, or None for all roles.

    Returns:
        A list of warning dicts, each with keys: timestamp, role,
        warning, text_preview.
    """
    if role:
        return [w for w in _PARSE_WARNING_LOG if w["role"] == role]
    return list(_PARSE_WARNING_LOG)


def _classify_severity(count: int) -> str:
    """Classify warning frequency into a severity label.

    Thresholds:
        high:   >= 5 warnings in the window (urgent — prompt needs tightening)
        medium: >= 2 warnings in the window (monitor — degradation starting)
        low:    < 2 warnings (acceptable — occasional failures are normal)
    """
    if count >= 5:
        return "high"
    if count >= 2:
        return "medium"
    return "low"


def _get_parse_warnings_by_severity(role: str | None = None) -> dict[str, list[dict]]:
    """[Bug #25] Return parse warnings grouped by severity.

    Severity is based on the count of warnings per role within the current
    rolling log window (max _PARSE_WARNING_LOG_MAX entries):
        high:   >= 5 warnings — prompt likely needs immediate tightening
        medium: >= 2 warnings — degradation starting, monitor
        low:    < 2 warnings   — occasional failures, acceptable

    Args:
        role: Optional role filter. If given, only that role's warnings
            are counted and returned.

    Returns:
        Dict with keys "high", "medium", "low", each mapping to a list of
        warning dicts. Each warning dict is augmented with a "severity" key.
    """
    warnings = _get_parse_warnings(role)
    # Count per role to determine severity
    role_counts: dict[str, int] = {}
    for w in warnings:
        r = w.get("role", "unknown")
        role_counts[r] = role_counts.get(r, 0) + 1

    result: dict[str, list[dict]] = {"high": [], "medium": [], "low": []}
    for w in warnings:
        r = w.get("role", "unknown")
        sev = _classify_severity(role_counts.get(r, 0))
        w_with_sev = {**w, "severity": sev}
        result[sev].append(w_with_sev)
    return result


def _clear_parse_warnings() -> None:
    """Clear parse warning log. Primarily for testing isolation."""
    _PARSE_WARNING_LOG.clear()
