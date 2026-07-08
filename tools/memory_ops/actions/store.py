"""tools/memory_ops/actions/store.py — Store action handler.
v1.1: Removed dead compress_result import. Use helpers.cfg for mock propagation.
v1.3: Added chunked store path (chunk=True → store_chunked() via chonkie).
"""
from __future__ import annotations

from tools.memory_ops import helpers
from tools.memory_ops.helpers import _mem, _validate_tags, _validate_memory_type, _validate_collections
from tools.memory_ops._registry import register_action
from core.contracts import ok, fail

# v1.3: Reuse _chunk_text from the file tool (same chonkie integration, already tested).
# This import is safe — read_file.py is already loaded at server boot by the
# registry auto-discovery scan. The chonkie import inside _chunk_text is lazy
# (soft dependency), so this import does NOT make chonkie a hard dependency.
# See: docs/tools/file/INSTRUCTIONS.md rule #25 — "reuse _chunk_text() from read_file.py"
from tools.file_ops.actions.read_file import _chunk_text


@register_action("memory", "store", help_text="Save a memory (text, memory_type, importance, tags, goal, outcome, tools_used, source). v1.3: chunk=True splits text via chonkie into linked chunks.")
def run_store(text="", memory_type="", tags="", collections=None, importance=5, trace_id="", goal="", outcome="", tools_used="", source="", **kwargs):
    if not text:
        return fail("text is required for store", trace_id=trace_id)

    is_valid, err = _validate_tags(tags, max_count=helpers.cfg.max_tags_per_entry)
    if not is_valid:
        return fail(err, trace_id=trace_id)

    is_valid, err = _validate_memory_type(memory_type)
    if not is_valid:
        return fail(err, trace_id=trace_id)

    is_valid, err = _validate_collections(collections)
    if not is_valid:
        return fail(err, trace_id=trace_id)

    text_bytes = len(text.encode("utf-8"))
    if text_bytes > helpers.cfg.memory_max_entry_bytes:
        return fail(
            f"text is {text_bytes} bytes — exceeds limit of {helpers.cfg.memory_max_entry_bytes}",
            trace_id=trace_id,
        )

    if importance < 1 or importance > 10:
        return fail(f"importance must be 1-10, got {importance}", trace_id=trace_id)

    # ── v1.3: Chunked store path ──────────────────────────────────────────
    # When chunk=True, the input text is split into N chunks via chonkie
    # (TokenChunker or SentenceChunker). Each chunk is stored as a separate
    # memory with shared source_doc_id metadata, enabling precise recall
    # (find the specific paragraph, not the whole document).
    #
    # Chunking is RESTRICTED to semantic + episodic collections:
    #   - procedural has a reinforcement feature (increment reinforcement_count
    #     on semantic match) that is nonsensical for chunks — which chunk
    #     gets reinforced? Reject with a clear error.
    #
    # The core's execute_store_chunked() skips vector dedup (chunks from the
    # same document would falsely trigger it) and does hash dedup only.
    # See: core/memory_backend/write_ops.py → execute_store_chunked()
    chunk = kwargs.get("chunk", False)
    if chunk:
        chunk_method = kwargs.get("chunk_method", "token")
        chunk_size = kwargs.get("chunk_size", 512)

        # Reject chunking on procedural — reinforcement is nonsensical for chunks
        if memory_type == "procedural":
            return fail(
                "chunk=True is not supported on procedural memories "
                "(reinforcement conflict — use semantic or episodic instead)",
                trace_id=trace_id,
            )

        # Split text into chunks via chonkie (soft dependency — lazy import)
        try:
            chunks = _chunk_text(text, chunk_method, chunk_size)
        except (RuntimeError, ValueError) as e:
            return fail(f"Chunking failed: {e}", trace_id=trace_id)

        if not chunks:
            return fail("Chunking produced 0 chunks — text may be empty or too short", trace_id=trace_id)

        store = _mem()
        result = store.store_chunked(
            chunks=chunks, memory_type=memory_type, importance=importance,
            tags=tags, trace_id=trace_id, goal=goal, outcome=outcome,
            tools_used=tools_used, source=source,
        )
        return ok(result, trace_id=trace_id)

    # ── Standard (non-chunked) store path ─────────────────────────────────
    store = _mem()
    result = store.store(
        text=text, memory_type=memory_type, importance=importance,
        tags=tags, trace_id=trace_id, goal=goal, outcome=outcome,
        tools_used=tools_used, source=source,
    )
    return ok(result, trace_id=trace_id)
