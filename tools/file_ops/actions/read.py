"""
Read file action handler.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from core.config import cfg
from tools.file_ops.helpers import _safe_resolve

def _read_file(path_str: str, max_chars: int = 50_000) -> dict:
    """Read a file with agent-root-first search, symlink safety, and extension validation."""
    resolved = None

    # 1. If relative, try agent root first (source code lives here)
    if not Path(path_str).is_absolute():
        candidate = cfg.agent_root / path_str
        if candidate.exists():
            candidate = candidate.resolve()          # follow symlinks
            if candidate.is_relative_to(cfg.agent_root):
                resolved = candidate

    # 2. Then try workspace root
    if resolved is None and not Path(path_str).is_absolute():
        candidate = cfg.workspace_root / path_str
        if candidate.exists():
            candidate = candidate.resolve()
            if candidate.is_relative_to(cfg.workspace_root):
                resolved = candidate

    # 3. Fallback to absolute/explicit path via existing safe resolver
    if resolved is None:
        resolved = _safe_resolve(path_str)[0]

    if not resolved:
        return {"status": "error", "error": "File not found or access denied"}

    # Extension check on the REAL file (after symlink resolution)
    ALLOWED_EXTENSIONS = {
        ".txt", ".py", ".md", ".json", ".yaml", ".yml", ".toml", ".cfg", ".ini",
        ".log", ".csv", ".tsv", ".html", ".css", ".js", ".xml", ".svg",
    }
    if resolved.suffix.lower() not in ALLOWED_EXTENSIONS:
        return {"status": "error", "error": f"File type not allowed: {resolved.suffix}"}

    # --- original reading logic (unchanged) ---
    if not resolved.exists():
        return {"status": "error", "error": f"File not found: {resolved}"}
    if not resolved.is_file():
        return {"status": "error", "error": f"Not a file: {resolved}"}

    stat = resolved.stat()
    if stat.st_size == 0:
        return {
            "status": "success", "path": str(resolved),
            "content": "", "size": 0, "lines": 0, "truncated": False,
        }

    try:
        text = resolved.read_text(encoding="utf-8", errors="replace")
        truncated = len(text) > max_chars
        if truncated:
            text = text[:max_chars] + f"\n\n[...truncated — {stat.st_size} bytes total]"

        return {
            "status":    "success",
            "path":      str(resolved),
            "content":   text,
            "size":      stat.st_size,
            "lines":     text.count("\n") + 1,
            "truncated": truncated,
            "extension": resolved.suffix,
        }
    except Exception as e:
        return {"status": "error", "error": f"Read failed: {e}", "path": str(resolved)}