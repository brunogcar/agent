"""validators.py — Output validators for benchmark tasks.

Each validator returns a float 0.0-1.0.
"""
from __future__ import annotations

import ast
import difflib
import io
import json
import re
import sys
from typing import Any


def _strip_markdown(text: str) -> str:
    """Strip ```lang fences from code blocks. Handles any language tag."""
    text = text.strip()
    m = re.match(r"^```[a-zA-Z]*\r?\n?(.*?)```\s*$", text, re.DOTALL)
    if m:
        return m.group(1).strip()
    return text


def _resolve_expected(expected, validator_fn, output, **kwargs):
    """Handle expected as str or list[str]. Returns max score across all references."""
    if isinstance(expected, list):
        if not expected:
            return 0.0
        return max(validator_fn(output, exp=e, **kwargs) for e in expected)
    return validator_fn(output, exp=expected, **kwargs)


def validate_exact_match(output: str, expected: str = "", **kwargs) -> float:
    """Exact case-insensitive match. Supports multi-reference expected as list."""
    def _match(output, exp, **kw):
        return 1.0 if output.strip().lower() == exp.strip().lower() else 0.0
    return _resolve_expected(expected, _match, output)


def validate_contains(output: str, expected: str = "", **kwargs) -> float:
    """Case-insensitive substring match. Supports multi-reference expected as list."""
    def _match(output, exp, **kw):
        return 1.0 if exp.strip().lower() in output.strip().lower() else 0.0
    return _resolve_expected(expected, _match, output)


def validate_fuzzy_match(output: str, expected: str = "", threshold: float = 0.6, **kwargs) -> float:
    """Partial credit based on string similarity. Supports multi-reference expected as list."""
    def _match(output, exp, **kw):
        out = output.strip().lower()
        exp = exp.strip().lower()
        if out == exp:
            return 1.0
        if exp.startswith("[") and exp.endswith("]"):
            return 1.0 if out == exp else 0.0
        similarity = difflib.SequenceMatcher(None, out, exp).ratio()
        return 1.0 if similarity >= threshold else similarity
    return _resolve_expected(expected, _match, output, threshold=threshold)


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


def validate_python_execution(output: str, test_cases: list[str] = None, **kwargs) -> float:
    """Execute Python code and run test cases. Restricted namespace, no stdout leak.

    Uses a finally block to guarantee stdout is always restored even on unexpected
    exceptions. Restricted builtins prevent dangerous calls (no print/open/import)
    while including common exceptions so correct implementations still work.
    """
    if not test_cases:
        return validate_python_ast(output)
    clean = _strip_markdown(output)
    if not clean:
        return 0.0

    # Restricted namespace: no print/open/import, but common exceptions allowed
    restricted = {
        "__builtins__": {
            "range": range, "len": len, "str": str, "int": int, "float": float,
            "list": list, "dict": dict, "set": set, "tuple": tuple, "type": type,
            "isinstance": isinstance, "abs": abs, "min": min, "max": max,
            "sum": sum, "round": round, "sorted": sorted, "enumerate": enumerate,
            "zip": zip, "map": map, "filter": filter, "any": any, "all": all,
            "chr": chr, "ord": ord, "pow": pow, "divmod": divmod, "bool": bool,
            # Base exceptions
            "Exception": Exception, "BaseException": BaseException,
            "AssertionError": AssertionError, "ValueError": ValueError,
            "TypeError": TypeError, "RuntimeError": RuntimeError,
            # Common exceptions implementations may raise internally
            "IndexError": IndexError, "KeyError": KeyError,
            "AttributeError": AttributeError, "NotImplementedError": NotImplementedError,
            "StopIteration": StopIteration, "ZeroDivisionError": ZeroDivisionError,
            "OverflowError": OverflowError, "RecursionError": RecursionError,
            "True": True, "False": False, "None": None,
        }
    }

    old_stdout = sys.stdout
    try:
        sys.stdout = io.StringIO()  # suppress any print() in submitted code
        ns = {}
        exec(clean, restricted, ns)

        passed = 0
        for test in test_cases:
            try:
                exec(test, restricted, ns)
                passed += 1
            except (AssertionError, Exception):
                pass

        return passed / len(test_cases)

    except SyntaxError:
        return 0.0
    except Exception:
        return 0.0
    finally:
        sys.stdout = old_stdout  # always restored, even on unexpected exceptions


def validate_keyword_coverage(output: str, expected_keywords: list[str] = None, **kwargs) -> float:
    """Coverage of expected keywords. Case-insensitive, whole-word match."""
    if not expected_keywords:
        return 1.0
    text = output.lower()
    found = 0
    for kw in expected_keywords:
        kw_lower = kw.lower()
        # Primary: whole-word match
        if re.search(r'\b' + re.escape(kw_lower) + r'\b', text):
            found += 1
        else:
            # Fallback: normalize spaces/hyphens and retry
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


def validate_composite(output: str, min_steps: int = 0, required_keywords: list = None, must_appear_before: list = None, pattern: str = "", **kwargs) -> float:
    """Composite validator: regex + step count + keywords + ordering."""
    scores = []

    # 1. Regex pattern (format check)
    if pattern:
        scores.append(1.0 if re.search(pattern, output, re.MULTILINE) else 0.0)

    # 2. Minimum steps — counts BOTH numbered lists AND bullets
    if min_steps > 0:
        numbered = re.findall(r'^\s*\d+[\.)]\s+\S', output, re.MULTILINE)
        bullets = re.findall(r'^\s*[-•*]\s+\S', output, re.MULTILINE)
        total_steps = len(numbered) + len(bullets)
        scores.append(min(total_steps / min_steps, 1.0))

    # 3. Keyword coverage (with word boundaries)
    if required_keywords:
        text = output.lower()
        found = 0
        for kw in required_keywords:
            if re.search(r'\b' + re.escape(kw.lower()) + r'\b', text):
                found += 1
        scores.append(found / len(required_keywords))

    # 4. Ordering: first keyword must appear before second
    if must_appear_before:
        text_lower = output.lower()
        order_hits = 0
        for pair in must_appear_before:
            if len(pair) == 2:
                first, second = pair[0].lower(), pair[1].lower()
                fp = text_lower.find(first)
                sp = text_lower.find(second)
                if fp != -1 and sp != -1 and fp < sp:
                    order_hits += 1
        scores.append(order_hits / len(must_appear_before))

    return sum(scores) / len(scores) if scores else 0.0


# ─────────────────────────────────────────────────────────────────────────────
# Agent-mode validators (v1.3)
# These validators work with JSON output from agent-mode tasks (where the
# LLM outputs structured JSON matching a role's json_schema, not raw text).
# ─────────────────────────────────────────────────────────────────────────────

def validate_json_field(output: str, field: str = "", sub_validator: str = "exact_match", **kwargs) -> float:
    """Extract a field from JSON output, then run another validator on it.

    Used in agent-mode: the LLM outputs JSON (e.g., {"analysis": "...", "patch": "def foo()...", ...}),
    and this validator extracts the "patch" field and runs python_execution on it.

    Args:
        output: Raw LLM output (should be valid JSON or JSON in markdown fences).
        field: JSON key to extract (e.g., "patch", "test_code", "refactored_code").
        sub_validator: Name of the validator to run on the extracted field.
        **kwargs: Passed to the sub-validator (e.g., test_cases, expected).

    Returns:
        0.0 if JSON parse fails or field is missing.
        Otherwise, the sub-validator's score on the extracted field.
    """
    if not field:
        return 0.0
    clean = _strip_markdown(output)
    try:
        data = json.loads(clean)
    except (json.JSONDecodeError, ValueError):
        return 0.0
    if not isinstance(data, dict) or field not in data:
        return 0.0
    field_value = data[field]
    if not isinstance(field_value, str):
        field_value = str(field_value)
    # Run the sub-validator on the extracted field
    sub_fn = VALIDATORS.get(sub_validator, VALIDATORS["exact_match"])
    return sub_fn(field_value, **kwargs)


def validate_schema_match(output: str, schema: dict = None, **kwargs) -> float:
    """Validate that output matches a JSON schema (manual check — no jsonschema dependency).

    Checks:
    1. Output is valid JSON (0.0 if not)
    2. All required fields are present (0.5 if missing any)
    3. Fields have correct types (0.75 if type mismatch)
    4. additionalProperties: False — no extra fields (0.9 if extras present)
    5. Full match = 1.0

    Args:
        output: Raw LLM output.
        schema: JSON schema dict with "properties", "required", "additionalProperties".

    Returns:
        0.0-1.0 score.
    """
    if not schema:
        return 0.0
    clean = _strip_markdown(output)
    try:
        data = json.loads(clean)
    except (json.JSONDecodeError, ValueError):
        return 0.0
    if not isinstance(data, dict):
        return 0.0

    properties = schema.get("properties", {})
    required = schema.get("required", [])

    # Check required fields
    missing = [k for k in required if k not in data]
    if missing:
        return 0.5

    # Check types
    type_map = {
        "string": str, "integer": int, "number": (int, float),
        "boolean": bool, "array": list, "object": dict,
    }
    type_errors = 0
    for key, prop in properties.items():
        if key not in data:
            continue
        expected_type = prop.get("type")
        if expected_type:
            # Handle union types like ["string", "null"]
            if isinstance(expected_type, list):
                valid_types = []
                for t in expected_type:
                    if t == "null":
                        valid_types.append(type(None))
                    else:
                        valid_types.append(type_map.get(t))
                if not any(isinstance(data[key], t) for t in valid_types if t):
                    type_errors += 1
            else:
                expected_py = type_map.get(expected_type)
                if expected_py and not isinstance(data[key], expected_py):
                    # Special case: bool is subclass of int in Python
                    if not (expected_type == "integer" and isinstance(data[key], bool)):
                        type_errors += 1
    if type_errors > 0:
        return 0.75

    # Check additionalProperties
    if schema.get("additionalProperties") is False:
        extra = [k for k in data if k not in properties]
        if extra:
            return 0.9

    # Check enum values
    enum_errors = 0
    for key, prop in properties.items():
        if key in data and "enum" in prop:
            if data[key] not in prop["enum"]:
                enum_errors += 1
    if enum_errors > 0:
        return 0.8

    return 1.0


VALIDATORS = {
    "exact_match": validate_exact_match,
    "contains": validate_contains,
    "fuzzy_match": validate_fuzzy_match,
    "json_valid": validate_json_valid,
    "python_ast": validate_python_ast,
    "python_execution": validate_python_execution,
    "keyword_coverage": validate_keyword_coverage,
    "regex_match": validate_regex_match,
    "composite": validate_composite,
    "json_field": validate_json_field,
    "schema_match": validate_schema_match,
}
