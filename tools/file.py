"""
tools/file.py — File meta-tool.

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
  write_pdf → write text to PDF using fpdf2

All paths are resolved relative to workspace_root unless absolute.
Paths outside workspace_root and agent_root are rejected for safety.
"""

from __future__ import annotations

import time
from typing import Optional

from core.config import cfg
from registry import tool

# Import helpers
from tools.file_ops.helpers import _safe_resolve

# Import action handlers
from tools.file_ops.actions.read import _read_file
from tools.file_ops.actions.write import _handle_write
from tools.file_ops.actions.list import _handle_list
from tools.file_ops.actions.backup import _handle_backup
from tools.file_ops.actions.read_many import _handle_read_many
from tools.file_ops.actions.search import _handle_search
from tools.file_ops.actions.read_pdf import _handle_read_pdf
from tools.file_ops.actions.write_pdf import _handle_write_pdf
from tools.file_ops.actions.read_docx import _handle_read_docx
from tools.file_ops.actions.write_docx import _handle_write_docx
from tools.file_ops.actions.read_xlsx import _handle_read_xlsx
from tools.file_ops.actions.write_xlsx import _handle_write_xlsx
from tools.file_ops.actions.read_pptx import _handle_read_pptx
from tools.file_ops.actions.write_pptx import _handle_write_pptx
from tools.file_ops.actions.patch import _handle_patch

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
    title:       str      = "",
    **kwargs
) -> dict:
    """
    File tool — read, write, search, and manage files.

    action: "read" | "write" | "list" | "backup" | "read_many" | "search" |
            "read_pdf" | "write_pdf" |
            "read_docx" | "write_docx" |
            "read_xlsx" | "write_xlsx" |
            "read_pptx" | "write_pptx" |
            "patch"

    read
        Read a single file. Paths relative to agent and workspace roots.
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
        Full-text search across agent and workspace files.
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
        file(action="write", path="output/report.md", content="# Report\n...")
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
        return _handle_write(path=path, content=content)

    # ── list ──────────────────────────────────────────────────────────────────
    if action == "list":
        return _handle_list(path=path)

    # ── backup ────────────────────────────────────────────────────────────────
    if action == "backup":
        return _handle_backup(path=path)

    # ── read_many ─────────────────────────────────────────────────────────────
    if action == "read_many":
        return _handle_read_many(paths=paths, mode=mode, max_chars=max_chars)

    # ── search ────────────────────────────────────────────────────────────────
    if action == "search":
        return _handle_search(query=query, max_results=max_results)

    # ── read_pdf ──────────────────────────────────────────────────────────────
    if action == "read_pdf":
        return _handle_read_pdf(path=path, max_chars=max_chars)

    # ── write_pdf ─────────────────────────────────────────────────────────────
    if action == "write_pdf":
        return _handle_write_pdf(path=path, content=content, title=title, max_chars=max_chars)

    # ── read_docx ─────────────────────────────────────────────────────────────
    if action == "read_docx":
        return _handle_read_docx(path=path, max_chars=max_chars)

    # ── write_docx ────────────────────────────────────────────────────────────
    if action == "write_docx":
        return _handle_write_docx(path=path, content=content, title=title)

    # ── read_xlsx ─────────────────────────────────────────────────────────────
    if action == "read_xlsx":
        return _handle_read_xlsx(path=path, max_chars=max_chars)

    # ── write_xlsx ────────────────────────────────────────────────────────────
    if action == "write_xlsx":
        return _handle_write_xlsx(path=path, content=content)

    # ── read_pptx ─────────────────────────────────────────────────────────────
    if action == "read_pptx":
        return _handle_read_pptx(path=path, max_chars=max_chars)

    # ── write_pptx ────────────────────────────────────────────────────────────
    if action == "write_pptx":
        return _handle_write_pptx(path=path, content=content)

    # ── patch (str_replace) ───────────────────────────────────────────────────
    if action == "patch":
        return _handle_patch(path=path, **kwargs)

    return {"status": "error", "error": f"Unknown action: {action}"}