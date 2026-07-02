"""Store action — save a memory to one of three typed collections."""
from __future__ import annotations

from core.contracts import ok, fail
from core.utils import compress_result

from tools.memory_ops._registry import register_action
from tools.memory_ops import helpers
from tools.memory_ops.helpers import _mem, _validate_tags, _validate_memory_type, _validate_collections

HELP_STORE = """
store — Save a memory to one of three typed collections.

Parameters:
  text (required): Memory content to store.
  memory_type (default "semantic"): Target collection — episodic | semantic | procedural.
  importance (default 5): Base score 1–10. Higher = slower decay.
  tags: Comma-separated tags. Max cfg.max_tags_per_entry.
  trace_id: Trace identifier for logging and correlation.
  goal: What was being attempted (episodic/procedural).
  outcome: success | failure | partial | unknown.
  tools_used: Comma-separated tool names (episodic).
  source: Source attribution (semantic), e.g. URL.

Examples:
  memory(action="store", memory_type="episodic",
         text="Fixed SyntaxError in tools/web.py",
         importance=8, goal="fix scraping bug", outcome="success")
  memory(action="store", memory_type="semantic",
         text="ChromaDB get_or_create_collection is idempotent",
         importance=7, tags="chromadb,startup")
"""


@register_action(
    "memory", "store",
    help_text=HELP_STORE,
    examples=[
        'memory(action="store", memory_type="episodic", text="Fixed bug", importance=8)',
        'memory(action="store", memory_type="semantic", text="ChromaDB is idempotent", tags="chromadb")',
    ],
)
def run_store(
    text: str = "",
    memory_type: str = "semantic",
    importance: int = 5,
    tags: str = "",
    trace_id: str = "",
    goal: str = "",
    outcome: str = "unknown",
    tools_used: str = "",
    source: str = "",
    collections=None,
    **kwargs,
) -> dict:
    """Store a memory entry with validation and deduplication."""
    if not text or not text.strip():
        return fail("text is required for store", trace_id=trace_id)

    if importance < 1 or importance > 10:
        return fail(f"importance must be 1-10, got {importance}", trace_id=trace_id)

    # Guard against storing huge blobs that bloat the vector DB
    text_bytes = len(text.encode("utf-8"))
    if text_bytes > helpers.cfg.memory_max_entry_bytes:
        return fail(
            f"text is {text_bytes} bytes — exceeds {helpers.cfg.memory_max_entry_bytes} byte limit. "
            "Summarise or chunk the content before storing.",
            trace_id=trace_id,
        )

    # Validate collections to prevent silent all-collections fallback
    is_valid, err = _validate_collections(collections)
    if not is_valid:
        return fail(err, trace_id=trace_id)

    # MED-05: Validate tags for store operation
    is_valid, err = _validate_tags(tags, max_count=helpers.cfg.max_tags_per_entry)
    if not is_valid:
        return fail(err, trace_id=trace_id)

    # Fail-fast: reject invalid memory_type before backend silent coercion
    is_valid, err = _validate_memory_type(memory_type)
    if not is_valid:
        return fail(err, trace_id=trace_id)

    store = _mem()
    result = store.store(
        text=text,
        memory_type=memory_type,
        importance=importance,
        tags=tags,
        trace_id=trace_id,
        goal=goal,
        outcome=outcome,
        tools_used=tools_used,
        source=source,
    )

    return ok(result, trace_id=trace_id)
