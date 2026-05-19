"""
Write file action handler.
"""

from __future__ import annotations

import shutil
from pathlib import Path

from core.config import cfg
from tools.file_ops.helpers import _safe_resolve

def _handle_write(path: str = "", content: str = "", **kwargs) -> dict:
    """Write content to a file. Auto-creates parent directories."""
    p, err = _safe_resolve(path)
    if err:
        return {"status": "error", "error": err}
    if not content and content != "":
        return {"status": "error", "error": "content is required for write"}
    if cfg.is_protected(p):
        return {"status": "error", "error": f"'{p.name}' is protected — edit manually"}

    backup_path = ""
    p.parent.mkdir(parents=True, exist_ok=True)

    # Auto-backup if file exists
    if p.exists():
        bak = p.with_suffix(p.suffix + ".bak")
        shutil.copy2(p, bak)
        backup_path = str(bak)

    try:
        p.write_text(content, encoding="utf-8")
        return {
            "status":      "success",
            "path":        str(p),
            "size":        len(content.encode("utf-8")),
            "backup_path": backup_path,
            "lines":       content.count("\n") + 1,
        }
    except Exception as e:
        return {"status": "error", "error": f"Write failed: {e}"}