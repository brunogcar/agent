"""
Summarize-context node for autocode workflow.

[v2.0] Phase 4 — compresses debug_history before re-entering the debug loop.
Without this, debug_history grows unboundedly across iterations and blows the
LLM context budget (#37). This node is wired into the graph between debug
iterations to produce a compact `debug_summary` string that downstream nodes
can read instead of the full history.

Soft dependency on chonkie (SentenceChunker) — lazily imported. If chonkie is
not installed or chunking fails, falls back to truncation (last 3 entries as
JSON). The fallback keeps the node usable in environments where chonkie is
not yet pip-installed (e.g., CI without optional deps).

Entry shape assumed: {iteration: int, phase: str, root_cause: str, fix: str,
                      tests_passed: bool, [confidence: str]}.
"""
from __future__ import annotations
import json
from typing import Any

from core.tracer import tracer
from workflows.autocode_impl.state import AutocodeState, _get_tdd


def _summarize_debug_history(history: list[dict]) -> str:
    """[v2.0] Phase 4 — compress debug_history into a single summary string.

    Strategy:
      1. Reverse the history so the most recent iteration comes first
         (the freshest hypothesis is the most relevant for the next iteration).
      2. Render each entry as a single sentence.
      3. Try chonkie SentenceChunker (soft dependency, lazy import). If it
         succeeds, return the FIRST chunk only (most recent) — keeps the
         summary tight and bounded.
      4. Fallback: JSON-serialize the last 3 entries (most recent first).

    Returns:
        A non-empty summary string. Returns "" if history is empty.
    """
    if not history:
        return ""

    # Reverse — most recent first.
    reversed_history = list(reversed(history))

    # Render each entry as a single sentence for the chunker.
    lines = []
    for entry in reversed_history:
        iteration = entry.get("iteration", "?")
        phase = entry.get("phase", "?")
        root_cause = entry.get("root_cause", "?")
        fix_preview = (entry.get("fix", "") or "")[:80]
        tests_passed = entry.get("tests_passed", False)
        # Include swarm confidence if present (swarm path only).
        confidence = entry.get("confidence")
        suffix = f" confidence={confidence}" if confidence else ""
        lines.append(
            f"iter={iteration} phase={phase} tests_passed={tests_passed}{suffix} "
            f"root_cause={root_cause} fix_preview={fix_preview}"
        )
    text = ". ".join(lines) + "."

    # Try chonkie SentenceChunker (soft dependency, lazy import).
    try:
        from chonkie import SentenceChunker  # type: ignore[import-not-found]
        chunker = SentenceChunker(chunk_size=512, chunk_overlap=0)
        chunks = chunker.chunk(text)
        if chunks:
            # Take the first chunk (most recent, since we reversed).
            return str(chunks[0])
    except Exception:
        # Soft dependency — silently fall back to truncation. Do not log at
        # warning level here because this is expected in environments without
        # chonkie installed (the caller already traced entry count).
        pass

    # Fallback: last 3 entries (most recent first) as JSON.
    last_three = reversed_history[:3]
    return json.dumps(last_three, ensure_ascii=False, default=str)


def node_summarize_context(state: AutocodeState) -> dict:
    """[v2.0] Phase 4 — compress debug_history before re-entering the debug loop.

    Reads `debug_history` from the TDD sub-state (with legacy fallback via
    _get_tdd), produces a compact summary via _summarize_debug_history, and
    writes it back as `debug_summary` in the TDD sub-state. Downstream nodes
    (debug, verify) can read `debug_summary` instead of the full history to
    keep context bounded (#37).

    This node does NOT mutate debug_history — the full history is preserved
    for the architecture-question exit check in node_systematic_debug.

    Returns:
        Partial state update `{"tdd": {"debug_summary": summary}}`.
    """
    tid = state.get("trace_id", "")
    debug_history = _get_tdd(state, "debug_history", []) or []

    if not debug_history:
        tracer.step(tid, "summarize_context", "Empty debug_history — no summary to produce")
        # [Hardening P0.1] Read-modify-write: returning {"tdd": {"debug_summary": ""}}
        # clobbers the entire tdd sub-state (LangGraph replaces dict values,
        # doesn't deep-merge). Preserve existing fields.
        current_tdd = dict(state.get("tdd", {}))
        current_tdd["debug_summary"] = ""
        return {"tdd": current_tdd}

    summary = _summarize_debug_history(debug_history)
    tracer.step(
        tid, "summarize_context",
        f"Compressed {len(debug_history)} debug_history entries into {len(summary)} chars"
    )
    # [Hardening P0.1] Read-modify-write: returning {"tdd": {"debug_summary": summary}}
    # clobbers the entire tdd sub-state (LangGraph replaces dict values,
    # doesn't deep-merge). Preserve existing fields like debug_history.
    current_tdd = dict(state.get("tdd", {}))
    current_tdd["debug_summary"] = summary
    return {"tdd": current_tdd}
