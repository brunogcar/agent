"""Context trimming helpers for agent tool."""
from __future__ import annotations

from core.config import cfg

_KEEP_HEAD_CHARS = 2000  # Preserve original goal/objective
_KEEP_TAIL_CHARS = 4000  # Preserve recent tool interactions


def _estimate_tokens(text: str) -> int:
    """Estimate token count for the given text.

    Tries tiktoken first (fast, accurate for OpenAI models), then transformers
    tokenizer if available, then falls back to chars/4 heuristic.

    The fallback is conservative: code tokenizes at ~3 chars/token, prose at ~4.
    Using 4 is safe but may under-utilize the budget for code-heavy contexts.
    """
    if not text:
        return 0

    # Try tiktoken (lightweight, no torch dependency)
    try:
        import tiktoken
        enc = tiktoken.get_encoding("cl100k_base")  # GPT-4 / Claude compatible
        return len(enc.encode(text))
    except Exception:
        pass

    # Try transformers tokenizer (if available, e.g. for local models)
    try:
        from transformers import AutoTokenizer
        # Use a generic fast tokenizer; actual model tokenizer is better
        # but requires knowing the model name at config time.
        tok = AutoTokenizer.from_pretrained("gpt2", use_fast=True)
        return len(tok.encode(text))
    except Exception:
        pass

    # Fallback: chars/4 heuristic (conservative for most content)
    return len(text) // 4


def _max_context_chars() -> int:
    """Return the current max context character budget (fallback heuristic).

    Dynamically derived from cfg.max_context_tokens so config reloads
    are respected without restarting the process.

    Note: This returns a CHARACTER budget for backward compatibility.
    New code should use _max_context_tokens() for token-accurate budgets.
    """
    tokens = getattr(cfg, "max_context_tokens", 8000)
    if tokens is None or not isinstance(tokens, (int, float)):
        tokens = 8000
    return int(max(1000, tokens)) * 4


def _max_context_tokens() -> int:
    """Return the current max context TOKEN budget.

    Uses cfg.max_context_tokens directly. Falls back to 8000 if invalid.
    """
    tokens = getattr(cfg, "max_context_tokens", 8000)
    if tokens is None or not isinstance(tokens, (int, float)):
        tokens = 8000
    return int(max(1000, tokens))


def _trim_context(text: str, max_chars: int | None = None, max_tokens: int | None = None) -> str:
    """Head+tail trim: preserves objective (head) and recent state (tail).

    CRITICAL: If the text contains a Python traceback, the traceback is
    preserved in full. Tracebacks are high-signal debugging content that
    must never be split across the truncation boundary.

    Args:
        text: The text to trim.
        max_chars: Maximum characters (legacy, for backward compatibility).
        max_tokens: Maximum tokens (preferred, uses accurate token counting).

    If max_tokens is provided, it takes precedence over max_chars.
    If neither is provided, uses _max_context_chars() as fallback.
    """
    if not text:
        return text

    # Determine budget
    if max_tokens is not None:
        budget = max_tokens
        budget_type = "tokens"
        text_tokens = _estimate_tokens(text)
        if text_tokens <= budget:
            return text
    elif max_chars is not None:
        budget = max_chars
        budget_type = "chars"
        if len(text) <= budget:
            return text
    else:
        budget = _max_context_chars()
        budget_type = "chars"
        if len(text) <= budget:
            return text

    # ── Traceback Preservation ─────────────────────────────────────────────
    tb_marker = "Traceback (most recent call last):"
    tb_start = text.find(tb_marker)

    if tb_start != -1:
        # Isolate the traceback block by walking lines — much more robust
        # than looking for \n\n, which fails on single-newline separators.
        tb_text = text[tb_start:]
        lines = tb_text.splitlines()
        tb_lines = [lines[0]]  # marker line
        seen_frame = False
        for line in lines[1:]:
            if line.startswith("  "):
                tb_lines.append(line)
                seen_frame = True
            elif not line.strip():
                tb_lines.append(line)
            elif seen_frame:
                # First non-empty, non-indented line after frames = exception
                tb_lines.append(line)
                break
            else:
                # Non-indented line before any frame — malformed, stop here
                break
        tb_text = "\n".join(tb_lines)

        if budget_type == "tokens":
            tb_tokens = _estimate_tokens(tb_text)
            tb_len = len(tb_text)
        else:
            tb_tokens = len(tb_text)
            tb_len = len(tb_text)

        if tb_tokens <= budget:
            # Full traceback fits — trim head to make room
            if budget_type == "tokens":
                head_budget_chars = int((budget - tb_tokens) * 4)
                head = text[:min(tb_start, head_budget_chars)]
            else:
                head_budget = max(0, budget - tb_len)
                head = text[:head_budget]

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

    # ── Normal Head+Tail Trim ──────────────────────────────────────────────
    if budget_type == "tokens":
        # Convert token budget to approximate char budget for slicing
        # Use conservative estimate: tokens * 5 chars/token max
        char_budget = budget * 5
    else:
        char_budget = budget

    if char_budget < _KEEP_HEAD_CHARS + _KEEP_TAIL_CHARS:
        head_budget = char_budget // 3
        tail_budget = char_budget - head_budget
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
