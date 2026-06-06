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

All paths are resolved relative to agent_root (the project) unless absolute 
or explicitly scoped to workspace. This prevents token-wasting search fallbacks.
Paths outside workspace_root and agent_root are rejected for safety.
"""
from __future__ import annotations

from registry import tool
from tools.file_ops._registry import DISPATCH
from core.path_guard import resolve_path, check_protected_file, make_path_error
from core.tracer import tracer

def _safe_dispatch_file(action: str, trace_id: str = "", **params) -> dict:
    """
    Dispatch file action through DISPATCH registry with path guards.
    """
    path = params.get("path", "")
    paths = params.get("paths", [])

    # 1. Validate single path
    if path:
        # Default to "agent" to fix the token-wasting "search workspace then agent" behavior
        resolved, err = resolve_path(path, default_root="agent")
        if not resolved:
            return make_path_error(path, action, err, trace_id)

        allowed, err = check_protected_file(resolved, action)
        if not allowed:
            return make_path_error(path, action, err, trace_id)

        # Pass the absolute, validated path to the handler
        params["path"] = str(resolved)

    # 2. Validate multiple paths (for read_many, etc.)
    elif paths:
        new_paths = []
        for p in paths:
            resolved, err = resolve_path(p, default_root="agent")
            if not resolved:
                return make_path_error(p, action, err, trace_id)
            allowed, err = check_protected_file(resolved, action)
            if not allowed:
                return make_path_error(p, action, err, trace_id)
            new_paths.append(str(resolved))
        params["paths"] = new_paths

    # 3. Dispatch to action handler
    if action in DISPATCH.get("file", {}):
        func = DISPATCH["file"][action]
        
        # [FIX] Defensive cleanup: ensure dispatcher metadata doesn't leak
        params.pop("action", None)
        
        try:
            return func(trace_id=trace_id, **params)
        except Exception as e:
            return {"status": "error", "error": str(e), "trace_id": trace_id}

    return {"status": "error", "error": f"Unknown file action: {action}", "trace_id": trace_id}

@tool
def file(
    action: str,
    path: str = "",
    paths: list[str] | None = None,
    content: str = "",
    query: str = "",
    max_chars: int | None = None,
    max_results: int | None = None,
    mode: str = "",
    old: str = "",
    new: str = "",
    trace_id: str = "",
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
        Returns: {content, size, lines, truncated}

    write
        Write content to a file. Auto-creates parent directories.
        If file exists, a .bak backup is created automatically.
        Required: path, content
        Returns: {path, size, backup_path}

    list
        List contents of a directory.
        Required: path (directory)
        Returns: {entries: [{name, type, size, modified}]}

    backup
        Copy a file with .bak suffix (manual backup).
        Required: path
        Returns: {original, backup}

    read_many
        Read multiple files concurrently. Returns all contents in one call.
        mode: "full" (default) | "summary" (first 500 chars per file)
        Required: paths (list of path strings)
        Optional: mode, max_chars
        Returns: {files: [{path, content, size, error}], count}

    search
        Full-text search across agent and workspace files.
        Builds/updates the index automatically on first use.
        Required: query
        Optional: max_results (default 10)
        Returns: {results: [{path, snippet, rank}], count}

    read_pdf
        Extract text from a PDF file using pdfplumber.
        Required: path
        Optional: max_chars
        Returns: {text, pages, truncated} 

    Examples:
        file(action="read", path="scripts/analysis.py")
        file(action="write", path="output/report.md", content="# Report\n...")
        file(action="list", path=".")
        file(action="read_many", paths=["a.py", "b.py", "c.py"], mode="summary")
        file(action="search", query="ChromaDB collection", max_results=5)
        file(action="read_pdf", path="docs/manual.pdf")
    """
    if not trace_id:
        trace_id = tracer.new_trace("file", goal=action)

    # 🔴 Cancellation Guard: Abort before any file mutations
    from core.runtime.cancellation import ensure_not_cancelled
    ensure_not_cancelled(trace_id)

    # Pack explicit parameters back into a dict for the dispatcher
    # Filter out empty strings/None to keep params clean
    params = {
        "path": path,
        "paths": paths,
        "content": content,
        "query": query,
        "max_chars": max_chars,
        "max_results": max_results,
        "mode": mode,
        "old": old,
        "new": new,
    }
    params = {k: v for k, v in params.items() if v not in ("", None, [])}
    
    return _safe_dispatch_file(action.strip().lower(), trace_id=trace_id, **params)