"""
Read Excel action handler.
"""

from __future__ import annotations

from pathlib import Path

from tools.file_ops.helpers import _safe_resolve
from tools.file_ops._registry import register_action

@register_action("file", "read_xlsx")
def _handle_read_xlsx(path: str = "", max_chars: int = 50_000, trace_id: str = "") -> dict:
    """Read an Excel file using pandas."""
    p, err = _safe_resolve(path)
    if err:
        return {"status": "error", "error": err}
    if not p.exists():
        return {"status": "error", "error": f"File not found: {p}"}
    if p.suffix.lower() not in (".xlsx", ".xls", ".xlsm"):
        return {"status": "error", "error": f"Not an Excel file: {p.name}"}

    try:
        import pandas as pd

        with pd.ExcelFile(str(p)) as xl:
            sheets = xl.sheet_names
            result = {}

            for sheet in sheets:
                df = xl.parse(sheet)
                MAX_ROWS = 200
                truncated_sheet = len(df) > MAX_ROWS
                if truncated_sheet:
                    df = df.head(MAX_ROWS)

                result[sheet] = {
                    "columns": df.columns.tolist(),
                    "rows": df.values.tolist(),
                    "shape": [len(df), len(df.columns)],
                    "truncated": truncated_sheet,
                    "dtypes": {c: str(t) for c, t in df.dtypes.items()},
                }

            first_df = xl.parse(sheets[0]) if sheets else None
            stats = {}
            if first_df is not None:
                num_cols = first_df.select_dtypes(include="number").columns.tolist()
                if num_cols:
                    stats = first_df[num_cols].describe().round(2).to_dict()

        return {
            "status":      "success",
            "path":        str(p),
            "sheets":      sheets,
            "sheet_count": len(sheets),
            "data":        result,
            "stats":       stats,
        }
    except ImportError:
        return {"status": "error", "error": "pandas not installed. Run: pip install pandas openpyxl"}
    except Exception as e:
        return {"status": "error", "error": f"XLSX read failed: {type(e).__name__}: {e}"}
