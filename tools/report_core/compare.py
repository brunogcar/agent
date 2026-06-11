"""
report_core/compare.py — Side-by-side diff table builder.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from tools.report_core.html import render_template, _write_manifest
from tools.report_core.paths import report_out_dir


def _compute_delta(before: Any, after: Any) -> tuple[str, str]:
    if before == after:
        return ("—", "neu")
    try:
        b = float(before) if before is not None else 0
        a = float(after) if after is not None else 0
        diff = a - b
        if diff > 0:
            return (f"+{diff:.2f}", "pos")
        elif diff < 0:
            return (f"{diff:.2f}", "neg")
        else:
            return ("—", "neu")
    except (ValueError, TypeError):
        pass
    if after is None and before is not None:
        return ("removed", "neg")
    if before is None and after is not None:
        return ("added", "pos")
    return ("changed", "neu")


def _diff_dicts(before: dict, after: dict) -> list[dict]:
    all_keys = sorted(set(before.keys()) | set(after.keys()))
    rows = []
    for key in all_keys:
        b = before.get(key, None)
        a = after.get(key, None)
        delta_str, delta_cls = _compute_delta(b, a)
        rows.append({
            "key": key,
            "before": b if b is not None else "—",
            "after": a if a is not None else "—",
            "delta": delta_str,
            "delta_class": delta_cls,
        })
    return rows


def _diff_tables(before: list[dict], after: list[dict], key_col: str = "") -> list[dict]:
    if not isinstance(before, list) or not isinstance(after, list):
        return []
    rows = []
    if key_col and before and key_col in before[0]:
        before_map = {str(row.get(key_col, i)): row for i, row in enumerate(before)}
        after_map = {str(row.get(key_col, i)): row for i, row in enumerate(after)}
        all_keys = sorted(set(before_map.keys()) | set(after_map.keys()))
        for k in all_keys:
            b_row = before_map.get(k, {})
            a_row = after_map.get(k, {})
            all_cols = sorted((set(b_row.keys()) | set(a_row.keys())) - {key_col})
            cell_diffs = []
            for col in all_cols:
                bv = b_row.get(col, None)
                av = a_row.get(col, None)
                ds, dc = _compute_delta(bv, av)
                cell_diffs.append({
                    "col": col,
                    "before": bv if bv is not None else "—",
                    "after": av if av is not None else "—",
                    "delta": ds,
                    "delta_class": dc,
                })
            rows.append({
                "row_key": k,
                "cells": cell_diffs,
                "status": "removed" if k not in after_map else "added" if k not in before_map else "changed",
            })
    else:
        max_len = max(len(before), len(after))
        for i in range(max_len):
            b_row = before[i] if i < len(before) else {}
            a_row = after[i] if i < len(after) else {}
            all_cols = sorted(set(b_row.keys()) | set(a_row.keys()))
            cell_diffs = []
            for col in all_cols:
                bv = b_row.get(col, None)
                av = a_row.get(col, None)
                ds, dc = _compute_delta(bv, av)
                cell_diffs.append({
                    "col": col,
                    "before": bv if bv is not None else "—",
                    "after": av if av is not None else "—",
                    "delta": ds,
                    "delta_class": dc,
                })
            rows.append({
                "row_key": str(i + 1),
                "cells": cell_diffs,
                "status": "removed" if i >= len(after) else "added" if i >= len(before) else "changed",
            })
    return rows


def build(trace_id: str, title: str, data: Any, config: dict) -> dict:
    out_dir = report_out_dir(trace_id)
    safe_title = "".join(c if c.isalnum() or c in "-_" else "_" for c in (title or "compare"))
    html_path = out_dir / f"{safe_title}.html"

    before = data.get("before") if isinstance(data, dict) else None
    after = data.get("after") if isinstance(data, dict) else None
    if before is None or after is None:
        raise ValueError("compare requires data={'before': ..., 'after': ...}")

    mode = "dict"
    diff_rows = []
    headers = []
    if isinstance(before, dict) and isinstance(after, dict):
        mode = "dict"
        diff_rows = _diff_dicts(before, after)
        headers = ["Key", "Before", "After", "Delta"]
    elif isinstance(before, list) and isinstance(after, list):
        if before and isinstance(before[0], dict):
            mode = "table"
            key_col = config.get("key_col", "")
            diff_rows = _diff_tables(before, after, key_col)
            if diff_rows and diff_rows[0]["cells"]:
                headers = ["Row"] + [c["col"] for c in diff_rows[0]["cells"]]
        else:
            mode = "list"
            max_len = max(len(before), len(after))
            for i in range(max_len):
                b = before[i] if i < len(before) else None
                a = after[i] if i < len(after) else None
                ds, dc = _compute_delta(b, a)
                diff_rows.append({
                    "index": i,
                    "before": b if b is not None else "—",
                    "after": a if a is not None else "—",
                    "delta": ds,
                    "delta_class": dc,
                })
            headers = ["Index", "Before", "After", "Delta"]
    else:
        raise ValueError(f"Unsupported compare types: {type(before).__name__} vs {type(after).__name__}")

    ctx = {
        "title": title,
        "subtitle": config.get("subtitle", ""),
        "mode": mode,
        "headers": headers,
        "rows": diff_rows,
        "theme": config.get("theme", "dark"),
        "accent": config.get("accent", "#0d9488"),
        "trace_id": trace_id,
        "before_label": config.get("before_label", "Before"),
        "after_label": config.get("after_label", "After"),
    }
    render_template("compare.html", ctx, html_path)
    _write_manifest(trace_id, action="compare", title=title, files=[html_path.name], config=config)

    return {
        "type": "compare",
        "title": title,
        "html_path": str(html_path),
        "mode": mode,
        "rows": len(diff_rows),
    }
