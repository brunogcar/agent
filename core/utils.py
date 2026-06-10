"""Shared utility helpers for tools and workflows."""
from __future__ import annotations
from typing import Any

_MAX_OUTPUT_CHARS = 4000  # Default truncation threshold for tool outputs


def truncate_output(text: str, max_chars: int = _MAX_OUTPUT_CHARS) -> str:
    """Truncate large tool outputs with a notice."""
    if not text or len(text) <= max_chars:
        return text
    return text[:max_chars] + f"\n\n[... {len(text) - max_chars} chars truncated; use raw output for full content ...]"


def _compress_value(value: Any, max_chars: int = _MAX_OUTPUT_CHARS) -> Any:
    """Recursively compress large string values in dicts/lists."""
    if isinstance(value, str) and len(value) > max_chars:
        return truncate_output(value, max_chars)
    if isinstance(value, dict):
        return {k: _compress_value(v, max_chars) for k, v in value.items()}
    if isinstance(value, list):
        return [_compress_value(v, max_chars) for v in value]
    return value


def compress_result(result: dict, max_chars: int = _MAX_OUTPUT_CHARS) -> dict:
    """Compress large string fields in a tool result dict."""
    if not isinstance(result, dict):
        return result
    return _compress_value(result, max_chars)