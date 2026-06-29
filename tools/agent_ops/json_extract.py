"""Brace-counting JSON extraction with dict-preference scoring.

When an LLM response contains prose before/after JSON, or wraps JSON in
markdown fences, this module extracts the first complete JSON object or array.

Algorithm:
 1. Fast path: try json.loads() on the full text.
 2. Scan for all { and [ positions, use depth tracking with string-boundary
    awareness to find complete structures.
 3. Validate each candidate with json.loads().
 4. Score candidates: prefer dicts (agent roles expect dict-root JSON),
    then prefer larger structures (handles prose with accidental {} before
    real JSON).

This is intentionally conservative: if no valid JSON is found, returns None
and lets the caller decide how to handle the failure.
"""
from __future__ import annotations

import json as _json


def _extract_first_json(text: str) -> str | None:
    """Extract first complete JSON object or array using brace/bracket counting.

    Handles nested structures, escaped quotes, and strings containing braces
    or brackets. Validates each candidate with json.loads before returning.

    Prefers dicts over arrays (since agent roles expect dict-root JSON),
    then the largest valid structure to handle arrays at root and
    prose with accidental {} before real JSON correctly.

    Args:
        text: Raw text that may contain JSON embedded in prose or markdown.

    Returns:
        The extracted JSON string, or None if no valid JSON was found.
    """
    # Fast path: the entire text is already valid JSON.
    try:
        _json.loads(text)
        return text
    except _json.JSONDecodeError:
        pass

    _MATCHING = {"{": "}", "[": "]"}
    # candidates is a list of (json_string, parsed_object) tuples.
    # Storing parsed objects avoids re-parsing during scoring.
    candidates: list[tuple[str, dict | list]] = []

    for opener in ("{", "["):
        closer = _MATCHING[opener]
        # Find all positions of the opener character in the text.
        positions = [i for i, c in enumerate(text) if c == opener]

        for start in positions:
            stack = []
            in_string = False
            escape = False

            for i in range(start, len(text)):
                c = text[i]
                if escape:
                    # Previous character was a backslash — this character is
                    # escaped (literal). Do NOT process it as a structural char.
                    # Just clear the escape flag and continue scanning.
                    escape = False
                    continue
                if c == "\\":
                    # Backslash starts an escape sequence. Set flag so the
                    # NEXT character is treated as literal.
                    escape = True
                    continue
                if c == '"':
                    # Unescaped quote toggles string mode.
                    in_string = not in_string
                    continue
                if in_string:
                    # Inside a JSON string — braces/brackets are literal.
                    continue
                if c == opener:
                    stack.append(c)
                elif c == closer:
                    if stack and stack[-1] == opener:
                        stack.pop()
                    # Check completion AFTER the pop, regardless of whether
                    # this specific closer matched (defensive for malformed input).
                    if not stack:
                        candidate = text[start:i + 1]
                        try:
                            parsed = _json.loads(candidate)
                            candidates.append((candidate, parsed))
                        except _json.JSONDecodeError:
                            pass  # Malformed structure, skip this candidate.
                        break  # Move to next opener position.

    if not candidates:
        return None

    def _score(item):
        """Score a candidate: dicts win over arrays, then larger wins."""
        candidate, parsed = item
        is_dict = isinstance(parsed, dict)
        return (is_dict, len(candidate))

    candidates.sort(key=_score, reverse=True)
    return candidates[0][0]
