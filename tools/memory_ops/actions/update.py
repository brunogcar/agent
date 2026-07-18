"""tools/memory_ops/actions/update.py — Update action handler. [NEW v1.4]

Modifies a memory by ID without delete+re-create. Tracks changes in a
sidecar SQLite audit table (rule_history) — NOT in ChromaDB metadata
(collective review: JSON string in metadata bloats queries + can't be
filtered natively).

v1.4 design (from collective review):
- Append-only audit log in SQLite (memory_db/memory_audit.db)
- The memory record itself is updated in-place (latest state is live)
- History is queryable: "show me all confidence changes for rule X"
- The audit table is exempt from ChromaDB — it's a relational concern

Usage:
  memory(action="update", id="abc123", fields={"importance": 8}, reason="reinforced")
  memory(action="update", id="abc123", fields={"confidence": 0.9, "tags": "source:sleep_learn"}, reason="boosted after 3 successes")
"""
from __future__ import annotations

import json
import time
import threading
from typing import Any

from core.contracts import ok, fail
from tools.memory_ops._registry import register_action
from tools.memory_ops.helpers import _mem
from core.config import cfg
from core.tracer import tracer


# v1.0 (P2 FIX): True singleton — was creating a new SQLite connection on
# every call. SQLite PersistentClient-style cost (file handle + page cache)
# multiplied per update. Now double-checked-locked at module level.
_audit_conn = None
_audit_lock = threading.Lock()


def _get_audit_db():
    """Lazy-init the SQLite audit database. Singleton per process.

    Uses the same memory_root as ChromaDB (memory_db/memory_audit.db).
    Thread-safe via double-checked locking + check_same_thread=False.
    """
    global _audit_conn
    if _audit_conn is not None:
        return _audit_conn
    with _audit_lock:
        if _audit_conn is not None:
            return _audit_conn
        import sqlite3
        db_path = cfg.memory_root / "memory_audit.db"
        _audit_conn = sqlite3.connect(str(db_path), check_same_thread=False)
        _audit_conn.row_factory = sqlite3.Row
        _audit_conn.execute("""
            CREATE TABLE IF NOT EXISTS rule_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                rule_id TEXT NOT NULL,
                changed_at INTEGER NOT NULL,
                field TEXT NOT NULL,
                old_value TEXT,
                new_value TEXT,
                reason TEXT,
                actor TEXT DEFAULT 'unknown'
            )
        """)
        _audit_conn.execute("CREATE INDEX IF NOT EXISTS idx_rule_id ON rule_history(rule_id)")
        _audit_conn.execute("CREATE INDEX IF NOT EXISTS idx_changed_at ON rule_history(changed_at)")
        _audit_conn.commit()
        return _audit_conn


# Fields that can be updated (whitelist — prevents arbitrary metadata writes)
_UPDATABLE_FIELDS = frozenset({
    "importance", "confidence", "tags", "goal", "outcome",
    "reasoning", "source", "tools_used", "enabled",
})


@register_action(
    "memory", "update",
    help_text="""update — Modify a memory by ID without delete+re-create. Tracks changes in an audit log.
Required: id, fields (dict of field→new_value), reason (why the change)
Optional: collection (which collection the ID lives in — default: search all), trace_id
Returns: {action_status: "updated", id, changed_fields: [...], version}

Updatable fields: importance, confidence, tags, goal, outcome, reasoning, source, tools_used, enabled
The change is logged to memory_db/memory_audit.db (rule_history table) — append-only, queryable.""",
    examples=[
        'memory(action="update", id="abc123", fields={"importance": 8}, reason="reinforced after success")',
        'memory(action="update", id="abc123", fields={"confidence": 0.9, "tags": "source:sleep_learn"}, reason="boosted")',
    ],
)
def run_update(
    id: str = "",
    fields: dict = None,
    reason: str = "",
    collection: str = "",
    trace_id: str = "",
    **kwargs,
) -> dict:
    """Update a memory record by ID, logging the change to the audit table."""
    if not id or not id.strip():
        return fail("id is required for update", trace_id=trace_id, error_code="MISSING_PARAM")
    if not fields or not isinstance(fields, dict):
        return fail("fields (dict) is required for update", trace_id=trace_id, error_code="MISSING_PARAM")
    if not reason.strip():
        return fail("reason is required for update (why the change?)", trace_id=trace_id, error_code="MISSING_PARAM")

    # Validate fields whitelist
    invalid = [k for k in fields if k not in _UPDATABLE_FIELDS]
    if invalid:
        return fail(
            f"Fields not updatable: {invalid}. Allowed: {sorted(_UPDATABLE_FIELDS)}",
            trace_id=trace_id, error_code="INVALID_PARAM",
        )

    # Validate importance range if present
    if "importance" in fields:
        try:
            imp = int(fields["importance"])
            if imp < 1 or imp > 10:
                return fail(f"importance must be 1-10, got {imp}", trace_id=trace_id, error_code="INVALID_PARAM")
            fields["importance"] = imp
        except (ValueError, TypeError):
            return fail(f"importance must be an int, got {type(fields['importance']).__name__}", trace_id=trace_id, error_code="INVALID_PARAM")

    # Validate confidence range if present
    if "confidence" in fields:
        try:
            conf = float(fields["confidence"])
            if conf < 0.0 or conf > 1.0:
                return fail(f"confidence must be 0.0-1.0, got {conf}", trace_id=trace_id, error_code="INVALID_PARAM")
            fields["confidence"] = conf
        except (ValueError, TypeError):
            return fail(f"confidence must be a float, got {type(fields['confidence']).__name__}", trace_id=trace_id, error_code="INVALID_PARAM")

    store = _mem()

    # Find the memory by ID — search the specified collection or all
    from core.memory_backend.constants import ALL_COLLECTIONS
    search_cols = [collection] if collection else ALL_COLLECTIONS
    found_col = None
    found_meta = None
    found_doc = None

    for col_name in search_cols:
        try:
            col = store._col(col_name)
            raw = col.get(ids=[id], include=["metadatas", "documents"])
            if raw.get("ids") and raw["ids"][0]:
                found_col = col_name
                found_meta = raw["metadatas"][0] if raw.get("metadatas") else {}
                found_doc = raw["documents"][0] if raw.get("documents") else ""
                break
        except Exception:
            continue

    if found_col is None:
        return fail(f"Memory with id {id!r} not found in {search_cols}", trace_id=trace_id, error_code="NOT_FOUND")

    # Apply updates + log to audit table
    now = int(time.time())
    changed_fields = []
    actor = kwargs.get("actor", "unknown")

    try:
        audit_conn = _get_audit_db()
    except Exception as e:
        tracer.error(trace_id, "memory_update", f"Audit DB init failed: {e}")
        return fail(f"Audit DB unavailable: {e}", trace_id=trace_id, error_code="INTERNAL_ERROR")

    for field, new_value in fields.items():
        old_value = found_meta.get(field, "")
        if str(old_value) == str(new_value):
            continue  # no change — skip

        # Log to audit table
        try:
            audit_conn.execute(
                "INSERT INTO rule_history (rule_id, changed_at, field, old_value, new_value, reason, actor) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (id, now, field, str(old_value), str(new_value), reason[:500], actor),
            )
        except Exception as e:
            tracer.error(trace_id, "memory_update", f"Audit log write failed: {e}")
            # Continue — the update is more important than the audit log

        # Apply to metadata
        found_meta[field] = new_value
        changed_fields.append(field)

    if not changed_fields:
        # v1.0: Do NOT close the singleton conn — it is shared across calls.
        return ok({
            "action_status": "noop",
            "action": "update",
            "id": id,
            "changed_fields": [],
            "note": "No changes — all fields already had the requested values",
            "trace_id": trace_id,
        }, trace_id=trace_id)

    # Increment version (v1.4: optimistic locking support)
    current_version = found_meta.get("version", 1)
    if isinstance(current_version, str):
        try:
            current_version = int(current_version)
        except ValueError:
            current_version = 1
    found_meta["version"] = current_version + 1
    found_meta["updated_at"] = now
    changed_fields.append("version")
    changed_fields.append("updated_at")

    # Write back to ChromaDB
    try:
        store._col(found_col).update(ids=[id], metadatas=[found_meta])
    except Exception as e:
        audit_conn.commit()
        return fail(f"ChromaDB update failed: {e}", trace_id=trace_id, error_code="INTERNAL_ERROR")

    audit_conn.commit()

    if trace_id:
        tracer.step(trace_id, "memory_update", f"Updated {id}: {changed_fields}")

    return ok({
        "action_status": "updated",
        "action": "update",
        "id": id,
        "collection": found_col,
        "changed_fields": changed_fields,
        "version": found_meta["version"],
        "trace_id": trace_id,
    }, trace_id=trace_id)
