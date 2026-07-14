"""Shared helpers for the autoresearch workflow.

v1.2.1 (P1-2): Extracted _extract_metric from setup.py + evaluate.py.
Both had identical regex logic — now a single source of truth.
"""
from __future__ import annotations

import re
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
