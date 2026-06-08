"""validators.py — Output validators for benchmark tasks.

Each validator returns a float 0.0-1.0.
"""
from __future__ import annotations

import ast
import json
import re
from typing import Any

def _strip_markdown(text: str) -> str:
    """Strip ```lang fences from code blocks. Handles any language tag."""
    text = text.strip()
    m = re.match(r'^```[a-zA-Z]*\r?\n?(.*?)```\s*$', text, re.DOTALL)
    if m:
        return m.group(1).strip()
    return text

def validate_exact_match(output: str, expected: str, **kwargs) -> float:
    """Exact case-insensitive match."""
    return 1.0 if output.strip().lower() == expected.strip().lower() else 0.0

def validate_contains(output: str, expected: str, **kwargs) -> float:
    """Case-insensitive substring match."""
    return 1.0 if expected.strip().lower() in output.strip().lower() else 0.0

def validate_fuzzy_match(output: str, expected: str, threshold: float = 0.6, **kwargs) -> float:
    """Partial credit based on string similarity."""
    import difflib
    out = output.strip().lower()
    exp = expected.strip().lower()
    if out == exp:
        return 1.0
    if exp.startswith("[") and exp.endswith("]"):
        return 1.0 if out == exp else 0.0
    similarity = difflib.SequenceMatcher(None, out, exp).ratio()
    return 1.0 if similarity >= threshold else similarity

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
    """Execute Python code and run test cases. Restricted namespace, no stdout leak."""
    if not test_cases:
        return validate_python_ast(output)
    clean = _strip_markdown(output)
    if not clean:
        return 0.0
    try:
        import io
        import sys
        
        # Suppress stdout during execution
        old_stdout = sys.stdout
        sys.stdout = io.StringIO()
        
        # Restricted namespace — no print, no dangerous builtins
        restricted = {"__builtins__": {"range": range, "len": len, "str": str, "int": int, "float": float, "list": list, "dict": dict, "set": set, "tuple": tuple, "type": type, "isinstance": isinstance, "abs": abs, "min": min, "max": max, "sum": sum, "round": round, "sorted": sorted, "enumerate": enumerate, "zip": zip, "map": map, "filter": filter, "any": any, "all": all, "chr": chr, "ord": ord, "pow": pow, "divmod": divmod, "bool": bool, "Exception": Exception, "AssertionError": AssertionError, "ValueError": ValueError, "TypeError": TypeError, "RuntimeError": RuntimeError, "True": True, "False": False, "None": None}}
        ns = {}
        exec(clean, restricted, ns)
        
        passed = 0
        for test in test_cases:
            try:
                exec(test, restricted, ns)
                passed += 1
            except AssertionError:
                pass
            except Exception:
                pass
        
        # Restore stdout
        sys.stdout = old_stdout
        return passed / len(test_cases)
    except SyntaxError:
        sys.stdout = old_stdout
        return 0.0
    except Exception:
        sys.stdout = old_stdout
        return 0.0

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
        numbered = re.findall(r'^\s*\d+[\.\)]\s+\S', output, re.MULTILINE)
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
}