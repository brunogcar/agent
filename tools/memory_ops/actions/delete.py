"""Delete action — remove memories by similarity query or explicit IDs."""
from __future__ import annotations

from core.contracts import ok, fail

from tools.memory_ops._registry import register_action
from tools.memory_ops.helpers import _mem

HELP_DELETE = """
delete — Remove memories by similarity query or explicit IDs.

Parameters:
  query (required): Search query to find memories to delete.
  collections: Filter to specific collections. Omit for all.
  threshold (default 0.0): Similarity threshold for deletion.
  confirm_ids: Specific IDs to delete (bypasses similarity search).
  trace_id: Trace identifier for logging and correlation.

Examples:
  memory(action="delete", query="old temporary data")
  memory(action="delete", query="stale entries", confirm_ids=["id1", "id2"])
"""


@register_action(
    "memory", "delete",
    help_text=HELP_DELETE,
    examples=[
        'memory(action="delete", query="old temporary data")',
        'memory(action="delete", query="stale entries", confirm_ids=["id1", "id2"])',
    ],
)
def run_delete(
    query: str = "",
    collections=None,
    threshold: float = 0.0,
    confirm_ids=None,
    trace_id: str = "",
    **kwargs,
) -> dict:
    """Delete memories by query or explicit IDs."""
    if not query:
        return fail("query is required for delete", trace_id=trace_id)

    store = _mem()
    result = store.delete(
        query=query,
        collections=collections,
        threshold=threshold or None,
        confirm_ids=confirm_ids,
    )

    return ok(result, trace_id=trace_id)
