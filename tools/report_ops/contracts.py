"""
report_ops/contracts.py - Standardized return contracts for report tool.
"""

from __future__ import annotations

from typing import Any


def report_ok(result: dict, trace_id: str = "") -> dict:
    """Wrap a successful report result with trace_id and standard fields."""
    out = dict(result)
    out["status"] = "success"
    out["trace_id"] = trace_id
    return out


def report_fail(message: str, trace_id: str = "") -> dict:
    """Standardized error return for report tool."""
    return {
        "status": "error",
        "error": message,
        "trace_id": trace_id,
    }
