"""tools/memory_ops/actions/delete.py — Delete action handler.
v1.2: confirm_ids type guard, threshold range check, tautology removed.
v1.4: source_doc_id group deletion — delete all chunks sharing a source_doc_id.
"""
from __future__ import annotations

from tools.memory_ops.helpers import _mem, _validate_collections
from tools.memory_ops._registry import register_action
from core.contracts import ok, fail

@register_action("memory", "delete", help_text="Remove memories by query, explicit IDs, or source_doc_id (group delete). v1.4: source_doc_id deletes all chunks in a group.")
def run_delete(query: str = "", collections=None, threshold=0.0, confirm_ids=None, source_doc_id: str = "", trace_id: str = "", **kwargs):
    # v1.4: source_doc_id group deletion
    if source_doc_id:
        return _delete_by_source_doc_id(source_doc_id, collections, trace_id)

    if not query and not confirm_ids:
        return fail("query, confirm_ids, or source_doc_id is required for delete", trace_id=trace_id)

    if confirm_ids is not None and not isinstance(confirm_ids, list):
        return fail(f"confirm_ids must be a list, got {type(confirm_ids).__name__}", trace_id=trace_id)

    is_valid, err = _validate_collections(collections)
    if not is_valid:
        return fail(err, trace_id=trace_id)

    if threshold < 0.0 or threshold > 1.0:
        return fail("threshold must be between 0.0 and 1.0", trace_id=trace_id)

    store = _mem()
    result = store.delete(
        query=query, collections=collections,
        threshold=threshold,
        confirm_ids=confirm_ids,
    )
    return ok(result, trace_id=trace_id)



def _delete_by_source_doc_id(source_doc_id: str, collections=None, trace_id: str = "") -> dict:
    """v1.4: Delete all memories sharing a source_doc_id (group delete).

    Searches all collections (or the specified subset) for memories with
    metadata.source_doc_id == source_doc_id, then deletes them all.
    Prevents orphaned fragments when cleaning up chunked memories.
    """
    from core.memory_backend.constants import ALL_COLLECTIONS

    if not source_doc_id or not source_doc_id.strip():
        return fail("source_doc_id is required", trace_id=trace_id, error_code="MISSING_PARAM")

    cols = collections if collections else ALL_COLLECTIONS
    store = _mem()

    found = []
    for col_name in cols:
        try:
            col = store._col(col_name)
            # ChromaDB metadata filter: exact match on source_doc_id
            raw = col.get(where={"source_doc_id": source_doc_id}, include=["metadatas"])
            ids = raw.get("ids", [])
            for id_ in ids:
                found.append({"id": id_, "collection": col_name})
        except Exception as e:
            from core.tracer import tracer
            tracer.warning(trace_id, "memory_delete", f"Collection {col_name} source_doc_id search failed: {e}")
            continue

    if not found:
        return ok({
            "action_status": "no_match",
            "action": "delete",
            "source_doc_id": source_doc_id,
            "deleted": 0,
            "trace_id": trace_id,
        }, trace_id=trace_id)

    # Delete them
    deleted = 0
    by_col = {}
    for entry in found:
        col_name = entry["collection"]
        try:
            store._col(col_name).delete(ids=[entry["id"]])
            deleted += 1
            by_col[col_name] = by_col.get(col_name, 0) + 1
        except Exception as e:
            from core.tracer import tracer
            tracer.error(trace_id, "memory_delete", f"Delete failed for {entry['id']}: {e}")

    from core.tracer import tracer
    if trace_id:
        tracer.step(trace_id, "memory_delete", f"Deleted {deleted} memories with source_doc_id={source_doc_id}")

    return ok({
        "action_status": "deleted",
        "action": "delete",
        "source_doc_id": source_doc_id,
        "deleted": deleted,
        "by_collection": by_col,
        "trace_id": trace_id,
    }, trace_id=trace_id)
