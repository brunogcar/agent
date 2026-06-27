"""report_core/data.py - Data loading with path guard and SSRF blocking.

Blocks all remote URLs and UNC paths. Only local files within the
allowed workspace/agent roots are permitted.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Optional, Tuple

from core.path_guard import resolve_path


def load_data(
    data: Any = None,
    data_path: str = "",
) -> Tuple[Optional[Any], str]:
    """
    Load data from inline dict/list or from a local file.
    Returns (data_object, error_string).
    """
    if data is not None:
        return data, ""

    if not data_path:
        return None, "Provide either data= (dict/list) or a local data_path="

    # SSRF guard: block URLs unconditionally
    lowered = data_path.lower().strip()
    if lowered.startswith(("http://", "https://", "ftp://", "file://")):
        return (
            None,
            "data_path must be a local file path. Use the web tool to fetch remote data first.",
        )

    # UNC path guard: block Windows network paths
    if lowered.startswith(("\\", "//")):
        return (
            None,
            "data_path must be a local file path. UNC paths are not allowed.",
        )

    p, err = resolve_path(data_path)
    if err:
        return None, err
    if not p.exists():
        return None, f"File not found: {p}"

    suffix = p.suffix.lower()

    try:
        if suffix == ".json":
            raw = json.loads(p.read_text(encoding="utf-8"))
            return raw, ""

        if suffix == ".csv":
            import pandas as pd  # lazy
            df = pd.read_csv(str(p))
            return df, ""

        if suffix in (".xlsx", ".xls"):
            import pandas as pd  # lazy
            df = pd.read_excel(str(p))
            return df, ""

        if suffix in (".db", ".sqlite", ".sqlite3"):
            # Return path string for SQLite - caller handles query in config
            return str(p), ""

        return None, f"Unsupported file type '{suffix}'. Use .csv, .json, .xlsx, .db"

    except Exception as e:
        return None, f"Failed to load {data_path}: {type(e).__name__}: {e}"
