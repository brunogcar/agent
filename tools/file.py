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

from registry import tool
from tools.file_ops._registry import DISPATCH

def _safe_dispatch_file(action: str, **params) -> dict:
    """
    Dispatch file action through DISPATCH registry.

    Args:
        action: Action name (read, write, list, etc.)
        **params: Action-specific parameters

    Returns:
        Result dictionary from the action function
    """
    if action in DISPATCH.get("file", {}):
        func = DISPATCH["file"][action]
        try:
            return func(**params)
        except Exception as e:
            return {"status": "error", "error": str(e)}
    return {"status": "error", "error": f"Unknown file action: {action}"}

@tool
def file(action: str, **kwargs) -> dict:
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
    return _safe_dispatch_file(action.strip().lower(), **kwargs)