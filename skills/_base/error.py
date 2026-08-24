"""skills/_base/error.py — Shared error section builder.

Extracted from 7 DDM skills that each had an identical 2-line
build_error_section function.

[Phase 4 C1] Centralizes the error section dict shape.
"""
from __future__ import annotations


def build_error_section(title: str, error: str) -> dict:
    """Build an error section (type=text with Portuguese message).

    Args:
        title: Section title (e.g. "Fluxo de investimento").
        error: The error message.

    Returns:
        {"type": "text", "title": title, "body": f"Erro ao consultar: {error}"}
    """
    return {"type": "text", "title": title,
            "body": f"Erro ao consultar: {error}"}
