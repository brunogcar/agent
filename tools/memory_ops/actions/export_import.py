"""tools/memory_ops/actions/export_import.py — Export/Import actions. [NEW v1.4]

JSONL backup/restore for memory collections. Needed for:
1. Migration (Commit 4: procedural_meta → procedural backup)
2. User-initiated backup/restore
3. Debugging (inspect what's stored)

Export format: one JSON object per line, each containing id + document + metadata + collection.
Import: reads JSONL, upserts each entry (dedup by ID — existing entries are updated, not duplicated).
"""
from __future__ import annotations

import json
import os
from pathlib import Path

from core.contracts import ok, fail
from tools.memory_ops._registry import register_action
from tools.memory_ops.helpers import _mem, _validate_collections
from core.memory_backend.constants import ALL_COLLECTIONS
from core.config import cfg
from core.tracer import tracer


@register_action(
    "memory", "export",
    help_text="""export — Export memories to a JSONL file (backup/migration).
Optional: collections (list — default: all), output_path (default: agent_root/memory_export.jsonl)
Returns: {action_status: "exported", file, count, collections}

Each line is a JSON object: {id, document, metadata, collection}""",
    examples=[
        'memory(action="export")',
        'memory(action="export", collections=["procedural"], output_path="backup.jsonl")',
    ],
)
def run_export(
    collections=None,
    output_path: str = "",
    trace_id: str = "",
    **kwargs,
) -> dict:
    """Export memories to a JSONL file."""
    is_valid, err = _validate_collections(collections)
    if not is_valid:
        return fail(err, trace_id=trace_id, error_code="INVALID_PARAM")

    cols = collections or ALL_COLLECTIONS
    store = _mem()

    if output_path:
        out = Path(output_path)
        if not out.is_absolute():
            out = cfg.agent_root / output_path
    else:
        out = cfg.agent_root / "memory_export.jsonl"

    total = 0
    by_col = {}

    try:
        with open(out, "w", encoding="utf-8") as f:
            for col_name in cols:
                try:
                    col = store._col(col_name)
                    raw = col.get(include=["documents", "metadatas"])
                    ids = raw.get("ids", [])
                    docs = raw.get("documents", [])
                    metas = raw.get("metadatas", [])

                    for id_, doc, meta in zip(ids, docs, metas):
                        entry = {
                            "id": id_,
                            "document": doc,
                            "metadata": meta or {},
                            "collection": col_name,
                        }
                        f.write(json.dumps(entry, default=str, ensure_ascii=False) + "\n")
                        total += 1

                    by_col[col_name] = len(ids)
                except Exception as e:
                    tracer.warning(trace_id, "memory_export", f"Collection {col_name} export failed: {e}")
                    by_col[col_name] = 0
    except Exception as e:
        return fail(f"Export failed: {e}", trace_id=trace_id, error_code="INTERNAL_ERROR")

    if trace_id:
        tracer.step(trace_id, "memory_export", f"Exported {total} memories to {out}")

    return ok({
        "action_status": "exported",
        "action": "export",
        "file": str(out),
        "count": total,
        "by_collection": by_col,
        "trace_id": trace_id,
    }, trace_id=trace_id)


@register_action(
    "memory", "import",
    help_text="""import — Import memories from a JSONL file (restore/migration).
Required: input_path (path to JSONL file)
Optional: collections (filter — only import these collections), trace_id
Returns: {action_status: "imported", file, imported, skipped, errors}

Format: one JSON object per line: {id, document, metadata, collection}
Existing IDs are updated (upsert); new IDs are inserted.""",
    examples=[
        'memory(action="import", input_path="backup.jsonl")',
        'memory(action="import", input_path="migration.jsonl", collections=["procedural"])',
    ],
)
def run_import(
    input_path: str = "",
    collections=None,
    trace_id: str = "",
    **kwargs,
) -> dict:
    """Import memories from a JSONL file."""
    if not input_path or not input_path.strip():
        return fail("input_path is required for import", trace_id=trace_id, error_code="MISSING_PARAM")

    inp = Path(input_path)
    if not inp.is_absolute():
        inp = cfg.agent_root / input_path
    if not inp.exists():
        return fail(f"File not found: {inp}", trace_id=trace_id, error_code="NOT_FOUND")

    is_valid, err = _validate_collections(collections)
    if not is_valid:
        return fail(err, trace_id=trace_id, error_code="INVALID_PARAM")

    filter_cols = set(collections) if collections else None
    store = _mem()
    imported = 0
    skipped = 0
    errors = 0

    try:
        with open(inp, "r", encoding="utf-8") as f:
            for line_num, line in enumerate(f, 1):
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                except json.JSONDecodeError as e:
                    errors += 1
                    tracer.warning(trace_id, "memory_import", f"Line {line_num}: JSON parse error: {e}")
                    continue

                col_name = entry.get("collection", "")
                if not col_name:
                    skipped += 1
                    continue
                if filter_cols and col_name not in filter_cols:
                    skipped += 1
                    continue

                try:
                    col = store._col(col_name)
                    col.upsert(
                        ids=[entry["id"]],
                        documents=[entry.get("document", "")],
                        metadatas=[entry.get("metadata", {})],
                    )
                    imported += 1
                except Exception as e:
                    errors += 1
                    tracer.warning(trace_id, "memory_import", f"Line {line_num}: upsert failed: {e}")
    except Exception as e:
        return fail(f"Import failed: {e}", trace_id=trace_id, error_code="INTERNAL_ERROR")

    if trace_id:
        tracer.step(trace_id, "memory_import", f"Imported {imported}, skipped {skipped}, errors {errors}")

    return ok({
        "action_status": "imported",
        "action": "import",
        "file": str(inp),
        "imported": imported,
        "skipped": skipped,
        "errors": errors,
        "trace_id": trace_id,
    }, trace_id=trace_id)
