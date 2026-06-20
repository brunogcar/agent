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


def _clear_parse_warnings() -> None:
    """Clear parse warning log. Primarily for testing isolation."""
    _PARSE_WARNING_LOG.clear()
