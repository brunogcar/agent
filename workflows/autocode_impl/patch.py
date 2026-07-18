"""
core/patch.py — Surgical str_replace patching for agent-managed files.

WHY THIS EXISTS
---------------
The autocode workflow used to write full file content on every edit. For large
files (400-1000 lines) that is extremely token-wasteful: the LLM sees the entire
file as input AND emits the entire file as output, even when only 5-10 lines
change. This module replaces that pattern with targeted str_replace patches.

THREE PUBLIC FUNCTIONS
----------------------
apply_patch(path, old, new)          — apply a single str_replace to a file
apply_patches(path, patches)         — apply a list of {old, new} dicts in order
extract_relevant_sections(text, hint)— return only the parts of a file relevant
                                       to a task hint, to shrink LLM input tokens

DESIGN DECISIONS
----------------
- str_replace only (no unified diff, no AST patching).
  Reason: LLMs are already trained to produce exact str_replace; unified diff
  line numbers are frequently wrong; AST requires language-specific parsers.

- old must appear EXACTLY ONCE.
  Reason: ambiguous matches would corrupt files silently. The caller must add
  enough surrounding context to make the match unique. We return the occurrence
  count on failure so the caller can diagnose.

- Atomic writes via tempfile.NamedTemporaryFile + os.replace.
  Reason: .bak files violate project rules and clutter the repo. Git provides
  versioning; atomic writes prevent corruption on crash. No .bak needed.

- extract_relevant_sections uses keyword overlap + context window expansion.
  Reason: no AST needed, language-agnostic, fast, good enough for LLM hints.
  The goal is to reduce a 1000-line file to the 100-200 lines that actually
  matter for the current task — 5-10x input token reduction.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path


# ── Result dataclasses ────────────────────────────────────────────────────────

@dataclass
class PatchResult:
    """
    Returned by apply_patch / apply_patches.
    Always check .ok before using other fields.
    """
    ok:           bool
    path:         str         = ""
    lines_changed: int        = 0
    backup_path:  str         = ""
    error:        str         = ""
    occurrences:  int         = 0   # >1 means old was ambiguous; 0 means not found


# ── Core patch logic ──────────────────────────────────────────────────────────

def apply_patch(path: Path, old: str, new: str) -> PatchResult:
    """
    Apply a single str_replace patch to `path`.

    Reads the file, finds `old` exactly once, replaces with `new`, writes back
    using an atomic write (tempfile + os.replace). No .bak backup is created —
    git provides versioning, and .bak files violate project rules.

    Returns PatchResult with ok=True on success, ok=False with .error on failure.

    IMPORTANT: `old` must be the EXACT text from the file — byte-for-byte.
    Copy-paste from the file; do not paraphrase or reformat. Include enough
    surrounding lines to guarantee uniqueness (at least 2-3 lines of context
    beyond the changed line itself).
    """
    if not old:
        return PatchResult(ok=False, error="'old' text is empty — nothing to replace")

    try:
        content = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return PatchResult(ok=False, error=f"file not found: {path}")
    except Exception as e:
        return PatchResult(ok=False, error=f"read error: {e}")

    # Count occurrences — must be exactly 1
    count = content.count(old)
    if count == 0:
        return PatchResult(
            ok=False,
            error=(
                f"'old' text not found in {path.name}. "
                "Ensure it is copied verbatim from the file (whitespace matters)."
            ),
            occurrences=0,
        )
    if count > 1:
        return PatchResult(
            ok=False,
            error=(
                f"'old' text appears {count} times in {path.name} — ambiguous. "
                "Add more surrounding lines to make it unique."
            ),
            occurrences=count,
        )

    # Compute lines_changed = max(old lines, new lines) as a rough metric
    old_lines = old.count("\n") + 1
    new_lines = new.count("\n") + 1 if new else 0
    lines_changed = max(old_lines, new_lines)

    updated = content.replace(old, new, 1)

    # [Bug #1] Atomic write — no .bak backup (violates project rules).
    # Git provides versioning; tempfile + os.replace prevents corruption on crash.
    import os
    import tempfile
    try:
        with tempfile.NamedTemporaryFile(
            mode='w', encoding='utf-8', dir=path.parent,
            delete=False, suffix='.tmp'
        ) as tmp:
            tmp.write(updated)
            tmp_path = Path(tmp.name)
        os.replace(tmp_path, path)
    except Exception as e:
        if 'tmp_path' in locals() and tmp_path.exists():
            tmp_path.unlink(missing_ok=True)
        return PatchResult(ok=False, error=f"write error: {e}")

    return PatchResult(
        ok=True,
        path=str(path),
        lines_changed=lines_changed,
    )


def apply_patches(path: Path, patches: list[dict]) -> PatchResult:
    """
    Apply multiple str_replace patches to the same file sequentially.

    `patches` is a list of {"old": str, "new": str} dicts.
    They are applied in order — each patch operates on the result of the previous.

    Stops and returns an error on the first failure (no partial-write risk —
    the file is only written after all patches succeed in memory).

    WHY SEQUENTIAL IN MEMORY: If we wrote after each patch, a failure mid-way
    would leave the file in a half-patched state. Instead we accumulate all
    changes in a string and write once at the end.
    """
    if not patches:
        return PatchResult(ok=False, error="no patches provided")

    try:
        content = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return PatchResult(ok=False, error=f"file not found: {path}")
    except Exception as e:
        return PatchResult(ok=False, error=f"read error: {e}")

    total_lines = 0
    for i, p in enumerate(patches):
        old = p.get("old", "")
        new = p.get("new", "")
        if not old:
            return PatchResult(ok=False, error=f"patch[{i}] has empty 'old'")

        count = content.count(old)
        if count == 0:
            return PatchResult(
                ok=False,
                error=f"patch[{i}] 'old' not found after applying {i} previous patches",
                occurrences=0,
            )
        if count > 1:
            return PatchResult(
                ok=False,
                error=f"patch[{i}] 'old' is ambiguous ({count} occurrences) — add context",
                occurrences=count,
            )

        content = content.replace(old, new, 1)
        total_lines += max(old.count("\n") + 1, new.count("\n") + 1 if new else 0)

    # [Bug #1] Atomic write — no .bak backup (violates project rules).
    import os
    import tempfile
    try:
        with tempfile.NamedTemporaryFile(
            mode='w', encoding='utf-8', dir=path.parent,
            delete=False, suffix='.tmp'
        ) as tmp:
            tmp.write(content)
            tmp_path = Path(tmp.name)
        os.replace(tmp_path, path)
    except Exception as e:
        if 'tmp_path' in locals() and tmp_path.exists():
            tmp_path.unlink(missing_ok=True)
        return PatchResult(ok=False, error=f"write error: {e}")

    return PatchResult(
        ok=True,
        path=str(path),
        lines_changed=total_lines,
    )


# ── Context extraction for token reduction ────────────────────────────────────

def extract_relevant_sections(
    content: str,
    hint: str,
    max_chars: int = 6000,
    context_lines: int = 15,
) -> str:
    """
    Return only the sections of `content` relevant to the task `hint`.

    HOW IT WORKS
    ------------
    1. Extract keywords from hint (words > 3 chars, lowercased, deduplicated).
    2. Score each line by how many keywords it contains.
    3. Expand high-scoring lines by ±context_lines to include surrounding
       context (function bodies, imports, etc.).
    4. Merge overlapping windows, add "..." separators between gaps.
    5. Truncate to max_chars.

    WHY THIS APPROACH
    -----------------
    A simple truncation (first N chars) misses functions near the end of the file.
    AST-based extraction requires language parsers.
    This keyword+context approach is language-agnostic, fast (microseconds),
    and dramatically reduces input tokens for large files where the LLM only
    needs to see the area it is editing.

    If hint is empty or no relevant lines are found, falls back to head truncation.
    """
    if not hint or not content:
        return content[:max_chars]

    lines = content.splitlines()
    if not lines:
        return content[:max_chars]

    # Extract meaningful keywords from the task hint
    # Filter short words and Python noise words that appear everywhere
    _STOPWORDS = {
        "the", "and", "for", "with", "this", "that", "from", "into",
        "when", "then", "each", "only", "also", "have", "been", "will",
        "should", "would", "could", "must", "make", "using", "used",
        "return", "pass", "true", "false", "none",
    }
    keywords = [
        w.lower() for w in re.split(r"\W+", hint)
        if len(w) > 3 and w.lower() not in _STOPWORDS
    ]
    keywords = list(dict.fromkeys(keywords))  # deduplicate, preserve order

    if not keywords:
        return content[:max_chars]

    # Score each line
    scored: list[tuple[int, int]] = []  # (line_index, score)
    for idx, line in enumerate(lines):
        line_lower = line.lower()
        score = sum(1 for kw in keywords if kw in line_lower)
        if score > 0:
            scored.append((idx, score))

    if not scored:
        # No keyword matches — return head truncation as fallback
        return content[:max_chars]

    # Build context windows around each matching line
    # Sort by score descending so highest-relevance areas are included first
    scored.sort(key=lambda x: -x[1])
    n = len(lines)
    included: set[int] = set()

    for idx, _score in scored:
        start = max(0, idx - context_lines)
        end   = min(n - 1, idx + context_lines)
        included.update(range(start, end + 1))

    # Build output: sorted line indices with "..." gap markers
    sorted_indices = sorted(included)
    result_parts: list[str] = []
    prev_idx = -2

    for idx in sorted_indices:
        if idx > prev_idx + 1:
            if result_parts:
                result_parts.append("...")
        result_parts.append(lines[idx])
        prev_idx = idx

    result = "\n".join(result_parts)

    # If the relevant sections still exceed max_chars, truncate with a note
    if len(result) > max_chars:
        result = result[:max_chars] + f"\n... (section truncated at {max_chars} chars)"

    return result
