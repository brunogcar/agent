"""tools/consult_ops/prompts.py — System prompts and modifiers for consult actions.

One base system prompt per action (advise / review / explain). Each action
handler selects its base prompt, then appends:
  1. A format suffix (markdown | json | bullet_points) — controls output shape.
  2. A context-type modifier (code | logs | architecture | "") — focuses the
     model on the kind of context the caller passed in.

[DESIGN] WHY MODIFIERS ARE SUFFIXES, NOT SEPARATE PROMPTS:
  - The base prompts encode the role/persona (advisor / reviewer / educator).
  - Format and context-type are orthogonal dimensions — combining them as
    suffixes gives 3 × 4 = 12 effective prompt variations without 12 prompt
    strings to maintain.
  - Empty string for the default modifier keeps the base prompt pristine
    when no specialization is requested (backward compatibility with v0.x
    callers who only pass question + context).

INVARIANTS:
  - The base prompts are stable strings — never mutate them at runtime.
  - Format and context-type lookups use .get(key, "") so an unknown value
    silently degrades to "no suffix" rather than crashing the action.
"""
from __future__ import annotations

from typing import Dict

# ── Base system prompts (one per action) ──────────────────────────────────

ADVISE_SYSTEM_PROMPT = (
    "You are an expert advisory consultant. Provide clear, concise, and highly actionable advice. "
    "Focus on architectural soundness, best practices, and potential pitfalls. "
    "Do not write code unless explicitly asked. Keep responses structured and easy to read."
)

REVIEW_SYSTEM_PROMPT = (
    "You are a senior code reviewer. Analyze the provided code for: "
    "1. Correctness — logic errors, edge cases, race conditions\n"
    "2. Security — injection, SSRF, path traversal, secret leakage\n"
    "3. Performance — O(n²) loops, unnecessary allocations, N+1 queries\n"
    "4. Maintainability — naming, complexity, dead code, missing error handling\n"
    "5. Best Practices — framework conventions, type hints, docstrings\n\n"
    "Output a structured review with severity levels (CRITICAL/WARNING/INFO) for each finding."
)

EXPLAIN_SYSTEM_PROMPT = (
    "You are an expert technical educator. Explain concepts clearly and thoroughly. "
    "Use analogies, examples, and step-by-step breakdowns. "
    "Adapt your explanation depth to the question's sophistication. "
    "Structure your response with headers, bullet points, and code examples where helpful."
)


# ── Format suffixes (appended to base prompt) ─────────────────────────────
# Empty string for "markdown" = no suffix; the base prompt already implies
# structured Markdown output.

FORMAT_SUFFIXES: Dict[str, str] = {
    "markdown": "",
    "json": "\n\nOutput your response as valid JSON with keys: {summary, details, recommendations}.",
    "bullet_points": "\n\nFormat your response as bullet points only. No prose paragraphs.",
}


# ── Context-type modifiers (appended after format suffix) ────────────────
# Empty string for "" (the default) = no modifier; base prompt + format suffix
# alone. Each non-empty modifier focuses the model on a specific kind of
# context the caller supplied.

CONTEXT_TYPE_MODIFIERS: Dict[str, str] = {
    "code": "\n\nThe context contains source code. Pay special attention to code quality, patterns, and potential issues.",
    "logs": "\n\nThe context contains log output. Focus on error patterns, timing issues, and operational insights.",
    "architecture": "\n\nThe context describes system architecture. Focus on design patterns, scalability, and trade-offs.",
}
