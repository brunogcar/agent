"""Helpers for the data workflow.

_extract_code_from_response: pull Python code out of an agent(role="code")
response. The code role is a JSON-mode role that returns {analysis, patch,
assumptions, tests}; we want the "patch" field. If structured parsing fails
(no parsed dict / no patch key), fall back to a markdown ```python``` fence
regex, then to raw text — logging each fallback so failures are observable
instead of silent.
"""
from __future__ import annotations

import re

from core.tracer import tracer

# [Fix #9] Module-level compiled regex (was `import re` inside node_execute).
# Matches a ```python\n ... ``` fenced block. Language tag is optional so a
# bare ``` fence also matches. Non-greedy + DOTALL so it spans newlines.
_CODE_FENCE_RE = re.compile(r"```(?:python)?\n(.*?)```", re.DOTALL)


def _extract_code_from_response(parsed: dict | None, text: str, trace_id: str = "") -> str:
    """Extract runnable Python code from an agent(role="code") response.

    Resolution order:
      1. parsed["patch"]   — structured JSON output (preferred)
      2. ```python``` fence — regex fallback when JSON parse failed
      3. raw text           — last resort

    [Fix #9] Each fallback is logged via tracer.warning so a malformed LLM
    response is observable instead of silently producing broken code that
    fails at execution with a confusing SyntaxError.

    Args:
        parsed: The "parsed" dict from the agent response (may be None/empty).
        text:   The raw text from the agent response.
        trace_id: Trace ID for warning logging.

    Returns:
        The extracted code string (never empty if any source had content).
    """
    # 1. Structured patch field (preferred).
    if parsed and isinstance(parsed, dict):
        patch = parsed.get("patch")
        if patch and isinstance(patch, str) and patch.strip():
            return patch

    # 2. Markdown ```python fence fallback.
    match = _CODE_FENCE_RE.search(text or "")
    if match:
        tracer.warning(
            trace_id, "execute",
            "Structured code parse failed — extracted code from ```python fence"
        )
        return match.group(1).strip()

    # 3. Raw text last resort.
    tracer.warning(
        trace_id, "execute",
        "Structured code parse failed and no code fence found — using raw text"
    )
    return text or ""
