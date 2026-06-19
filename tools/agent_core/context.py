"""Context trimming helpers for agent tool."""
from __future__ import annotations

from core.config import cfg

# ── Context trimming helper ───────────────────────────────────────────────────
# [BUGFIX-5] Derive char budget from cfg.max_context_tokens instead of hardcoding.
# Approx 4 chars per token is conservative for most tokenizers.
# Computed dynamically per-call so config reloads are respected.
_KEEP_HEAD_CHARS = 2000   # Preserve original goal/objective
_KEEP_TAIL_CHARS = 4000   # Preserve recent tool interactions

def _max_context_chars() -> int:
    """Return the current max context character budget.

    Dynamically derived from cfg.max_context_tokens so config reloads
    are respected without restarting the process.
    """
    return cfg.max_context_tokens * 4


def _trim_context(text: str, max_chars: int | None = None) -> str:
    """Head+tail trim: preserves objective (head) and recent state (tail).

    CRITICAL: If the text contains a Python traceback, the traceback is
    preserved in full. Tracebacks are high-signal debugging content that
    must never be split across the truncation boundary.
    """
    if max_chars is None:
        max_chars = _max_context_chars()

    if not text or len(text) <= max_chars:
        return text

    # ── Traceback Preservation ─────────────────────────────────────────────
    tb_marker = "Traceback (most recent call last):"
    tb_start = text.find(tb_marker)

    if tb_start != -1:
        # Traceback found — ensure it stays intact in the tail
        tb_text = text[tb_start:]
        # Find where traceback ends (next blank line or end of text)
        tb_end_rel = tb_text.find("\n\n")
        if tb_end_rel != -1:
            tb_text = tb_text[:tb_end_rel]

        tb_len = len(tb_text)

        if tb_len <= max_chars:
            # Full traceback fits — trim head to make room
            head_budget = max(0, max_chars - tb_len)
            head = text[:head_budget]
            # Clean break at paragraph boundary
            head_break = head.rfind("\n\n")
            if head_break != -1:
                head = head[:head_break]
            truncated = len(text) - len(head) - tb_len
            return (
                head
                + f"\n\n[... {truncated} chars of intermediate context truncated ...]\n\n"
                + tb_text
            )
        # else: traceback exceeds entire budget — fall through to normal trim
        # (tail will still capture the error line at the end)

    # ── Normal Head+Tail Trim ──────────────────────────────────────────────
    if max_chars < _KEEP_HEAD_CHARS + _KEEP_TAIL_CHARS:
        head_budget = max_chars // 3
        tail_budget = max_chars - head_budget
    else:
        head_budget = _KEEP_HEAD_CHARS
        tail_budget = _KEEP_TAIL_CHARS

    head = text[:head_budget]
    tail = text[-tail_budget:]
    head_break = head.rfind("\n\n")
    if head_break != -1:
        head = head[:head_break]
    tail_break = tail.find("\n")
    if tail_break != -1:
        tail = tail[tail_break + 1:]
    truncated = len(text) - len(head) - len(tail)
    return (
        head
        + f"\n\n[... {truncated} chars of intermediate context truncated ...]\n\n"
        + tail
    )

# ── Meta-tool ─────────────────────────────────────────────────────────────────
