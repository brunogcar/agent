"""
SQLite FTS index for full-text search.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Optional

from core.config import cfg

# ── SQLite FTS index ──────────────────────────────────────────────────────────

_INDEX_DB: Optional[sqlite3.Connection] = None

def _get_index() -> sqlite3.Connection:
    global _INDEX_DB
    if _INDEX_DB is None:
        cfg.workspace_index.mkdir(parents=True, exist_ok=True)
        db_path = cfg.workspace_index / "fts.db"
        _INDEX_DB = sqlite3.connect(str(db_path), check_same_thread=False)
        _INDEX_DB.execute("""
            CREATE VIRTUAL TABLE IF NOT EXISTS files_fts
            USING fts5(path, content, tokenize='porter ascii')
        """)
        _INDEX_DB.execute("""
            CREATE TABLE IF NOT EXISTS files_meta (
                path TEXT PRIMARY KEY,
                mtime REAL,
                size  INTEGER
            )
        """)
        _INDEX_DB.commit()
    return _INDEX_DB

def _index_file(path: Path) -> bool:
    """Add or update a file in the FTS index. Returns True on success."""
    try:
        stat  = path.stat()
        mtime = stat.st_mtime
        size  = stat.st_size

        if size > 500_000:  # skip files > 500KB
            return False

        db = _get_index()

        # Check if up to date
        row = db.execute(
            "SELECT mtime FROM files_meta WHERE path = ?", (str(path),)
        ).fetchone()
        if row and abs(row[0] - mtime) < 0.01:
            return True  # already indexed and unchanged

        text = path.read_text(encoding="utf-8", errors="replace")

        db.execute("DELETE FROM files_fts WHERE path = ?", (str(path),))
        db.execute("INSERT INTO files_fts(path, content) VALUES (?, ?)", (str(path), text))
        db.execute(
            "INSERT OR REPLACE INTO files_meta(path, mtime, size) VALUES (?, ?, ?)",
            (str(path), mtime, size),
        )
        db.commit()
        return True
    except Exception:
        return False

def _build_index(root: Path, extensions: set[str] = None) -> int:
    """Index all text files under root. Returns count indexed."""
    if extensions is None:
        extensions = {".py", ".md", ".txt", ".json", ".yaml", ".yml", ".toml", ".cfg", ".ini"}

    count = 0
    for p in root.rglob("*"):
        if p.is_file() and p.suffix in extensions:
            # Skip hidden, cache, git
            parts = p.parts
            if any(part.startswith(".") or part == "__pycache__" for part in parts):
                continue
            if _index_file(p):
                count += 1
    return count