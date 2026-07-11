"""[Autocode v2.0] Consolidated JSON extraction from LLM responses.

Replaces 3 duplicated implementations:
  - workflows/autocode_impl/helpers.py: _parse_json, _parse_json_array
  - core/router.py: _extract_first_json
  - core/llm_backend/client.py: _parse_response

All LLM JSON parsing in the codebase should route through these functions.
If a new edge case is found, fix it here once and all callers benefit.

Usage:
    from core.json_extract import extract_json, extract_json_array, extract_first_json

    data = extract_json(text)          # dict — returns {} on failure
    items = extract_json_array(text)   # list — returns [] on failure
    raw = extract_first_json(text)     # str | None — raw JSON string for deferred parsing
"""
from __future__ import annotations

import json
import re
from typing import Any

# Regex to find fenced code blocks (```json ... ``` or ``` ... ```)
_FENCE_PATTERN = re.compile(r"```(?:[^\n]*\n)?(.*?)```", re.DOTALL)


def _strip_fences(text: str) -> str:
    """Strip markdown code fences from text.

    Handles both ```json ... ``` and ``` ... ``` formats.
    """
    clean = text.strip()
    if clean.startswith("```json"):
        clean = clean[7:]
    elif clean.startswith("```"):
        clean = clean[3:]
    if clean.endswith("```"):
        clean = clean[:-3]
    return clean.strip()


def _extract_code_blocks(text: str) -> list[str]:
    """Extract all code block contents from markdown text."""
    return [m.group(1).strip() for m in _FENCE_PATTERN.finditer(text)]


def extract_json(text: str | None) -> dict:
    """Parse a JSON object from text, extracting from code blocks if needed.

    Tries (in order):
      1. Direct json.loads(text)
      2. Strip fences, then json.loads
      3. Extract from each code block, json.loads each
      4. Find first {...} substring via raw_decode

    Returns:
        Parsed dict, or {} if all attempts fail.
    """
    if not text:
        return {}

    # 1. Direct parse
    try:
        result = json.loads(text)
        if isinstance(result, dict):
            return result
    except json.JSONDecodeError:
        pass

    # 2. Strip fences, retry
    clean = _strip_fences(text)
    if clean != text:
        try:
            result = json.loads(clean)
            if isinstance(result, dict):
                return result
        except json.JSONDecodeError:
            pass

    # 3. Try each code block
    for block in _extract_code_blocks(text):
        try:
            result = json.loads(block)
            if isinstance(result, dict):
                return result
        except json.JSONDecodeError:
            continue

    # 4. Find first {...} via raw_decode (handles trailing text)
    try:
        for i, char in enumerate(clean):
            if char == "{":
                try:
                    obj, _ = json.JSONDecoder().raw_decode(clean[i:])
                    if isinstance(obj, dict):
                        return obj
                except json.JSONDecodeError:
                    continue
    except Exception:
        pass

    return {}


def extract_json_array(text: str | None) -> list:
    """Parse a JSON array from text, extracting from code blocks if needed.

    Same multi-strategy approach as extract_json but for arrays.

    Returns:
        Parsed list, or [] if all attempts fail.
    """
    if not text:
        return []

    # 1. Direct parse
    try:
        result = json.loads(text)
        if isinstance(result, list):
            return result
    except json.JSONDecodeError:
        pass

    # 2. Strip fences, retry
    clean = _strip_fences(text)
    if clean != text:
        try:
            result = json.loads(clean)
            if isinstance(result, list):
                return result
        except json.JSONDecodeError:
            pass

    # 3. Try each code block
    for block in _extract_code_blocks(text):
        try:
            result = json.loads(block)
            if isinstance(result, list):
                return result
        except json.JSONDecodeError:
            continue

    # 4. Find first [...] via raw_decode
    try:
        for i, char in enumerate(clean):
            if char == "[":
                try:
                    obj, _ = json.JSONDecoder().raw_decode(clean[i:])
                    if isinstance(obj, list):
                        return obj
                except json.JSONDecodeError:
                    continue
    except Exception:
        pass

    return []


def extract_first_json(text: str | None) -> str | None:
    """Extract the first valid JSON object as a raw string (for deferred parsing).

    Used when the caller needs the raw JSON string (e.g., to pass to a schema
    validator) rather than a parsed dict.

    Returns:
        Raw JSON string, or None if no valid JSON found.
    """
    if not text:
        return None

    # 1. Strip fences, try direct parse
    clean = _strip_fences(text)
    try:
        json.loads(clean)
        return clean
    except json.JSONDecodeError:
        pass

    # 2. Try each code block
    for block in _extract_code_blocks(text):
        try:
            json.loads(block)
            return block
        except json.JSONDecodeError:
            continue

    # 3. Find first {...} via raw_decode
    try:
        for i, char in enumerate(clean):
            if char == "{":
                try:
                    obj, end = json.JSONDecoder().raw_decode(clean[i:])
                    # Return the raw substring that parsed successfully
                    return clean[i:i + end]
                except json.JSONDecodeError:
                    continue
    except Exception:
        pass

    return None
