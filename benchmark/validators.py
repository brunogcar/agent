"""validators.py — Output validators for benchmark tasks.

Each validator returns a float 0.0-1.0.
"""
from __future__ import annotations

import ast
import json
import re
from typing import Any

def _strip_markdown(text: str) -> str:
    """Strip ```python / ```json / ``` fences from code blocks."""
    text = text.strip()
    if text.startswith("```python"):
        text = text[9:]
    elif text.startswith("```json"):
        text = text[7:]
    elif text.startswith("```"):
        text = text[3:]
    if text.endswith("```"):
        text = text[:-3]
    return text.strip()

def validate_exact_match(output: str, expected: str, **kwargs) -> float:
    """Exact case-insensitive match."""
    return 1.0 if output.strip().lower() == expected.strip().lower() else 0.0

def validate_json_valid(output: str, **kwargs) -> float:
    """Valid JSON. Strips markdown fences first. Optional schema check."""
    clean = _strip_markdown(output)
    try:
        data = json.loads(clean)
        schema = kwargs.get("schema")
        if schema:
            required = schema.get("required", [])
            missing = [k for k in required if k not in data]
            if missing:
                return 0.5
        return 1.0
    except (json.JSONDecodeError, ValueError):
        return 0.0

def validate_python_ast(output: str, **kwargs) -> float:
    """Valid Python AST. Strips markdown fences first."""
    clean = _strip_markdown(output)
    if not clean:
        return 0.0
    try:
        ast.parse(clean)
        return 1.0
    except SyntaxError:
        return 0.0

def validate_keyword_coverage(output: str, expected_keywords: list[str] = None, **kwargs) -> float:
    """Coverage of expected keywords. Case-insensitive, partial word match."""
    if not expected_keywords:
        return 1.0
    text = output.lower()
    found = 0
    for kw in expected_keywords:
        kw_lower = kw.lower()
        if kw_lower in text:
            found += 1
        else:
            # Normalize: remove spaces/hyphens and retry
            kw_norm = kw_lower.replace("-", "").replace(" ", "")
            text_norm = text.replace("-", "").replace(" ", "")
            if kw_norm in text_norm:
                found += 1
    return found / len(expected_keywords)

def validate_regex_match(output: str, pattern: str = "", **kwargs) -> float:
    """Match regex pattern."""
    if not pattern:
        return 1.0
    return 1.0 if re.search(pattern, output, re.MULTILINE) else 0.0

VALIDATORS = {
    "exact_match": validate_exact_match,
    "json_valid": validate_json_valid,
    "python_ast": validate_python_ast,
    "keyword_coverage": validate_keyword_coverage,
    "regex_match": validate_regex_match,
}
