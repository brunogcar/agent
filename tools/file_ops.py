"""
tools/file_ops.py — File meta-tool.

Replaces: fs MCP server for most operations (fs still exists for safety isolation)
The LLM sees ONE tool: file(action, ...)

Actions:
  read      → read a single file
  write     → write content to a file (auto-backup)
  list      → list directory contents
  backup    → copy file with .bak suffix
  read_many → read multiple files concurrently
  search    → full-text search across workspace (SQLite FTS)
  read_pdf  → extract text from PDF using pdfplumber

All paths are resolved relative to workspace_root unless absolute.
Paths outside workspace_root and agent_root are rejected for safety.
"""

from __future__ import annotations

import sqlite3
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Optional

from core.config import cfg
from registry import tool

# ── Path safety ───────────────────────────────────────────────────────────────

_ALLOWED_ROOTS = None

def _allowed_roots() -> list[Path]:
    global _ALLOWED_ROOTS
    if _ALLOWED_ROOTS is None:
        _ALLOWED_ROOTS = [
            cfg.workspace_root.resolve(),
            cfg.agent_root.resolve(),
        ]
    return _ALLOWED_ROOTS


def _resolve(path_str: str) -> Optional[Path]:
    """
    Resolve a path safely.
    - Absolute paths are used as-is (if within allowed roots)
    - Relative paths are resolved from workspace_root
    Returns None if the path escapes allowed roots.
    """
    p = Path(path_str)
    if not p.is_absolute():
        p = cfg.workspace_root / p

    resolved = p.resolve()
    for root in _allowed_roots():
        try:
            resolved.relative_to(root)
            return resolved
        except ValueError:
            continue
    return None  # path escapes allowed roots


def _safe_resolve(path_str: str) -> tuple[Optional[Path], str]:
    """Returns (resolved_path, error_message). error is "" on success."""
    if not path_str:
        return None, "path is required"
    p = _resolve(path_str)
    if p is None:
        return None, (
            f"Path '{path_str}' is outside allowed directories. "
            f"Use paths within workspace ({cfg.workspace_root}) or agent ({cfg.agent_root})."
        )
    return p, ""


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


# ── Read helpers ──────────────────────────────────────────────────────────────

def _read_file(path: Path, max_chars: int = 50_000) -> dict:
    """Read a single file and return structured result."""
    if not path.exists():
        return {"status": "error", "error": f"File not found: {path}"}
    if not path.is_file():
        return {"status": "error", "error": f"Not a file: {path}"}

    stat = path.stat()
    if stat.st_size == 0:
        return {
            "status": "success", "path": str(path),
            "content": "", "size": 0, "lines": 0, "truncated": False,
        }

    try:
        text = path.read_text(encoding="utf-8", errors="replace")
        truncated = len(text) > max_chars
        if truncated:
            text = text[:max_chars] + f"\n\n[...truncated — {stat.st_size} bytes total]"

        return {
            "status":    "success",
            "path":      str(path),
            "content":   text,
            "size":      stat.st_size,
            "lines":     text.count("\n") + 1,
            "truncated": truncated,
            "extension": path.suffix,
        }
    except Exception as e:
        return {"status": "error", "error": f"Read failed: {e}", "path": str(path)}


# ── Meta-tool ─────────────────────────────────────────────────────────────────

@tool
def file(
    action:    str,
    path:      str        = "",
    content:   str        = "",
    paths:     list       = None,
    mode:      str        = "full",
    query:     str        = "",
    max_chars: int        = 50_000,
    max_results: int      = 10,
) -> dict:
    """
    File tool — read, write, search, and manage files.

    action: "read" | "write" | "list" | "backup" | "read_many" | "search" | "read_pdf"

    read
        Read a single file. Paths relative to workspace root.
        Required: path
        Optional: max_chars (default 50000)
        Returns:  {content, size, lines, truncated}

    write
        Write content to a file. Auto-creates parent directories.
        If file exists, a .bak backup is created automatically.
        Required: path, content
        Returns:  {path, size, backup_path}

    list
        List contents of a directory.
        Required: path (directory)
        Returns:  {entries: [{name, type, size, modified}]}

    backup
        Copy a file with .bak suffix (manual backup).
        Required: path
        Returns:  {original, backup}

    read_many
        Read multiple files concurrently. Returns all contents in one call.
        mode: "full" (default) | "summary" (first 500 chars per file)
        Required: paths (list of path strings)
        Optional: mode, max_chars
        Returns:  {files: [{path, content, size, error}], count}

    search
        Full-text search across workspace files.
        Builds/updates the index automatically on first use.
        Required: query
        Optional: max_results (default 10)
        Returns:  {results: [{path, snippet, rank}], count}

    read_pdf
        Extract text from a PDF file using pdfplumber.
        Required: path
        Optional: max_chars
        Returns:  {text, pages, truncated}

    Examples:
        file(action="read", path="scripts/analysis.py")
        file(action="write", path="output/report.md", content="# Report\\n...")
        file(action="list", path=".")
        file(action="read_many", paths=["a.py", "b.py", "c.py"], mode="summary")
        file(action="search", query="ChromaDB collection", max_results=5)
        file(action="read_pdf", path="docs/manual.pdf")
    """
    action = action.strip().lower()

    # ── read ──────────────────────────────────────────────────────────────────
    if action == "read":
        p, err = _safe_resolve(path)
        if err:
            return {"status": "error", "error": err}
        return _read_file(p, max_chars)

    # ── write ─────────────────────────────────────────────────────────────────
    if action == "write":
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
            import shutil
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

    # ── list ──────────────────────────────────────────────────────────────────
    if action == "list":
        p, err = _safe_resolve(path or ".")
        if err:
            return {"status": "error", "error": err}
        if not p.is_dir():
            return {"status": "error", "error": f"Not a directory: {p}"}

        entries = []
        try:
            for item in sorted(p.iterdir()):
                stat = item.stat()
                entries.append({
                    "name":     item.name,
                    "type":     "dir" if item.is_dir() else "file",
                    "size":     stat.st_size if item.is_file() else 0,
                    "modified": time.strftime(
                        "%Y-%m-%d %H:%M", time.localtime(stat.st_mtime)
                    ),
                    "extension": item.suffix if item.is_file() else "",
                })
        except PermissionError as e:
            return {"status": "error", "error": f"Permission denied: {e}"}

        return {
            "status":  "success",
            "path":    str(p),
            "entries": entries,
            "count":   len(entries),
        }

    # ── backup ────────────────────────────────────────────────────────────────
    if action == "backup":
        import shutil
        p, err = _safe_resolve(path)
        if err:
            return {"status": "error", "error": err}
        if not p.exists():
            return {"status": "error", "error": f"File not found: {p}"}

        ts  = time.strftime("%Y%m%d_%H%M%S")
        bak = p.with_name(f"{p.stem}_{ts}{p.suffix}.bak")
        try:
            shutil.copy2(p, bak)
            return {"status": "success", "original": str(p), "backup": str(bak)}
        except Exception as e:
            return {"status": "error", "error": f"Backup failed: {e}"}

    # ── read_many ─────────────────────────────────────────────────────────────
    if action == "read_many":
        if not paths:
            return {"status": "error", "error": "paths list is required for read_many"}

        summary_chars = 500 if mode == "summary" else max_chars

        def _read_one(path_str: str) -> dict:
            p, err = _safe_resolve(path_str)
            if err:
                return {"path": path_str, "error": err, "content": "", "size": 0}
            result = _read_file(p, summary_chars)
            return {
                "path":    path_str,
                "content": result.get("content", ""),
                "size":    result.get("size", 0),
                "lines":   result.get("lines", 0),
                "error":   result.get("error", ""),
            }

        results = []
        # ThreadPoolExecutor for concurrent reads
        with ThreadPoolExecutor(max_workers=min(len(paths), 8)) as executor:
            futures = {executor.submit(_read_one, p): p for p in paths}
            for future in as_completed(futures):
                results.append(future.result())

        # Restore original order
        order  = {p: i for i, p in enumerate(paths)}
        results.sort(key=lambda r: order.get(r["path"], 999))

        total_size = sum(r["size"] for r in results)
        errors     = [r["path"] for r in results if r["error"]]

        return {
            "status":     "success",
            "files":      results,
            "count":      len(results),
            "total_size": total_size,
            "errors":     errors,
            "mode":       mode,
        }

    # ── search ────────────────────────────────────────────────────────────────
    if action == "search":
        if not query:
            return {"status": "error", "error": "query is required for search"}

        # Build/refresh index
        indexed = _build_index(cfg.workspace_root)

        try:
            db = _get_index()
            rows = db.execute(
                """
                SELECT path, snippet(files_fts, 1, '[', ']', '...', 20) as snippet, rank
                FROM files_fts
                WHERE content MATCH ?
                ORDER BY rank
                LIMIT ?
                """,
                (query, max_results),
            ).fetchall()

            results = [
                {"path": row[0], "snippet": row[1], "rank": round(abs(row[2]), 4)}
                for row in rows
            ]

            return {
                "status":        "success",
                "query":         query,
                "results":       results,
                "count":         len(results),
                "indexed_files": indexed,
            }
        except Exception as e:
            return {"status": "error", "error": f"Search failed: {e}"}

    # ── read_pdf ──────────────────────────────────────────────────────────────
    if action == "read_pdf":
        p, err = _safe_resolve(path)
        if err:
            return {"status": "error", "error": err}
        if not p.exists():
            return {"status": "error", "error": f"File not found: {p}"}
        if p.suffix.lower() != ".pdf":
            return {"status": "error", "error": f"Not a PDF file: {p.name}"}

        try:
            import pdfplumber

            pages_text = []
            with pdfplumber.open(str(p)) as pdf:
                total_pages = len(pdf.pages)
                for page in pdf.pages:
                    text = page.extract_text() or ""
                    if text.strip():
                        pages_text.append(text)

            full_text = "\n\n".join(pages_text)
            truncated = len(full_text) > max_chars
            if truncated:
                full_text = full_text[:max_chars] + f"\n\n[...truncated — {total_pages} pages total]"

            return {
                "status":    "success",
                "path":      str(p),
                "text":      full_text,
                "pages":     total_pages,
                "truncated": truncated,
                "word_count": len(full_text.split()),
            }
        except ImportError:
            return {"status": "error", "error": "pdfplumber not installed. Run: pip install pdfplumber"}
        except Exception as e:
            return {"status": "error", "error": f"PDF read failed: {type(e).__name__}: {e}"}

    return {
        "status": "error",
        "error":  f"Unknown action '{action}'. Use: read | write | list | backup | read_many | search | read_pdf",
    }
