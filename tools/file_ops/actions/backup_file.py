"""Backup file action handler."""

from __future__ import annotations

import shutil
import time
from pathlib import Path

from tools.file_ops.helpers import _safe_resolve
from tools.file_ops._registry import register_action


@register_action(
    "file",
    "backup_file",
    help_text="""Copy a file with timestamped .bak suffix (manual backup).
Required: path
Returns: {original, backup}""",
    examples=[
        'file(action="backup_file", path="config.yaml")',
    ],
)
def _handle_backup_file(path: str = "", trace_id: str = "", **kwargs) -> dict:
    """Copy a file with .bak suffix (manual backup)."""
    p, err = _safe_resolve(path)
    if err:
        return {"status": "error", "error": err}
    if not p.exists():
        return {"status": "error", "error": f"File not found: {p}"}

    ts = time.strftime("%Y%m%d_%H%M%S")
    bak = p.with_name(f"{p.stem}_{ts}{p.suffix}.bak")
    try:
        shutil.copy2(p, bak)
        return {"status": "success", "original": str(p), "backup": str(bak)}
    except Exception as e:
        return {"status": "error", "error": f"Backup failed: {e}"}
