"""
core/llm_backend/response.py — Unified LLM response object.

EXTRACTION NOTE (LLM Phase 1): Extracted from core/llm.py.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

@dataclass
class LLMResponse:
    """Unified response object returned by all LLM calls."""
    text:     str
    role:     str
    model:    str
    usage:    dict[str, int]
    elapsed:  float
    parsed:   Optional[Any]  = None
    error:    str            = ""
    ok:       bool           = True

    @classmethod
    def from_error(cls, role: str, model: str, error: str, elapsed: float = 0.0) -> "LLMResponse":
        return cls(
            text="", role=role, model=model,
            usage={"prompt": 0, "completion": 0, "total": 0},
            elapsed=elapsed, error=error, ok=False,
        )