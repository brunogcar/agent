<- Back to [File Overview](../FILE.md)

# 📝 API Reference

## 🔧 Tool Signature

```python
@tool
@meta_tool(DISPATCH["file"])
def file(
    action: Literal[
        "read_file", "write_file", "list_directory", "create_directory",
        "directory_tree", "move_file", "copy_file", "delete_file",
        "get_file_info", "exists", "patch_file", "edit_file",
        "append_file", "search_files", "find_files",
        "read_multiple_files", "read_media_file",
        "read_pdf", "write_pdf", "read_docx", "write_docx",
        "read_xlsx", "write_xlsx", "read_pptx", "write_pptx",
        "list_allowed_directories",
    ],
    path: str = "",
    paths: list[str] | None = None,
    content: str = "",
    query: str = "",
    pattern: str = "",
    max_chars: int | None = None,
    max_results: int | None = None,
    head: int | None = None,
    tail: int | None = None,
    max_depth: int | None = None,
    max_bytes: int | None = None,
    exclude_patterns: list[str] | None = None,
    old: str = "",
    new: str = "",
    edits: list[dict] | None = None,
    dry_run: bool = False,
    force: bool = False,
    recursive: bool = False,
    parents: bool = True,
    source: str = "",
    destination: str = "",
    trace_id: str = "",
) -> dict:
    """..."""
```

| Param | Type | Default | Description |
|-------|------|---------|-------------|
| `action` | `Literal[...]` | — | **Required.** Atomic action name. See Actions table below |
| `path` | `str` | `""` | File or directory path |
| `paths` | `list[str]` | `None` | Multiple paths (for `read_multiple_files`) |
| `content` | `str` | `""` | File content (for write actions) |
| `query` | `str` | `""` | Search query (for `search_files`) |
| `pattern` | `str` | `""` | Glob pattern (for `find_files`) |
| `max_chars` | `int` | `None` | Character limit for read actions |
| `max_results` | `int` | `None` | Result limit for search |
| `head` | `int` | `None` | Read first N lines |
| `tail` | `int` | `None` | Read last N lines |
| `max_depth` | `int` | `None` | Depth limit for `directory_tree` |
| `max_bytes` | `int` | `None` | Size limit for `read_media_file` (default 5MB) |
| `exclude_patterns` | `list[str]` | `None` | Glob patterns to exclude |
| `old` | `str` | `""` | Old text (for `patch_file`) |
| `new` | `str` | `""` | New text (for `patch_file`) |
| `edits` | `list[dict]` | `None` | Edit array (for `edit_file`) |
| `dry_run` | `bool` | `False` | Preview mode (for `edit_file`) |
| `force` | `bool` | `False` | Confirm destructive actions |
| `recursive` | `bool` | `False` | Recursive delete |
| `parents` | `bool` | `True` | Create parent directories |
| `source` | `str` | `""` | Source path (for `move_file`, `copy_file`) |
| `destination` | `str` | `""` | Destination path (for `move_file`, `copy_file`) |
| `trace_id` | `str` | `""` | Trace identifier |

---

## ⚡ Actions

### Read-Only Actions

| Action | Required Params | Optional Params | Description |
|--------|-----------------|-----------------|-------------|
| `read_file` | `path` | `max_chars`, `head`, `tail` | Read text file with line/char truncation. Max 10MB. |
| `list_directory` | `path` | — | List directory contents with metadata |
| `directory_tree` | `path` | `max_depth`, `exclude_patterns` | Recursive tree as structured JSON |
| `get_file_info` | `path` | — | File metadata (size, mode, times) |
| `exists` | `path` | — | Check if path exists |
| `search_files` | `query` | `max_results` | Full-text search across workspace |
| `find_files` | `pattern` | `path` | Glob pattern matching. Max 1000 results. |
| `read_multiple_files` | `paths` | `max_chars` | Concurrent multi-file read |
| `read_media_file` | `path` | `max_bytes` | Binary file → base64 + MIME type. Default 5MB. |
| `read_pdf` | `path` | `max_chars` | Extract text from PDF |
| `read_docx` | `path` | `max_chars` | Read Word document |
| `read_xlsx` | `path` | — | Read Excel spreadsheet |
| `read_pptx` | `path` | `max_chars` | Read PowerPoint |
| `list_allowed_directories` | — | — | Return allowed roots |

### Write Actions

| Action | Required Params | Optional Params | Description |
|--------|-----------------|-----------------|-------------|
| `write_file` | `path`, `content` | — | Write text file (auto-creates parents) |
| `append_file` | `path`, `content` | — | Append content without reading full file |
| `create_directory` | `path` | `parents` | Create directory |
| `move_file` | `source`, `destination` | `force` | Move/rename file or directory |
| `copy_file` | `source`, `destination` | `force` | Copy file or directory |
| `delete_file` | `path` | `force`, `recursive` | Delete file or directory |
| `patch_file` | `path`, `old`, `new` | — | Single str_replace |
| `edit_file` | `path`, `edits` | `dry_run` | Multi-edit with diff preview |
| `write_pdf` | `path`, `content` | `title` | Write text to PDF |
| `write_docx` | `path`, `content` | `title` | Write Word document |
| `write_xlsx` | `path`, `content` | — | Write Excel spreadsheet |
| `write_pptx` | `path`, `content` | — | Write PowerPoint |

---

### Action Details

#### `read_file` — Head, Tail, Max Chars

```python
# Full file (default)
file(action="read_file", path="app.py")

# First 50 lines
file(action="read_file", path="app.py", head=50)

# Last 20 lines (great for logs)
file(action="read_file", path="logs/app.log", tail=20)

# Character truncation
file(action="read_file", path="big.json", max_chars=10000)
```

Priority: `tail` > `head` > `max_chars`

**Size limit:** Files larger than 10MB are rejected before reading into memory.

#### `patch_file` vs `edit_file`

```python
# Single replacement — immediate apply
file(action="patch_file", path="app.py",
     old="def old():", new="def new():")

# Multiple edits — with diff preview
file(action="edit_file", path="app.py",
     edits=[
         {"oldText": "def a():", "newText": "def a_v2():"},
         {"oldText": "def b():", "newText": "def b_v2():"},
     ],
     dry_run=True)
```

**Note:** `oldText` replaces **all** occurrences in the file, not just the first match. This matches the MCP `edit_file` specification. For targeted single replacement, use `patch_file` instead.

#### `delete_file` — Force Required

```python
# Error — force not set
file(action="delete_file", path="tmp/old.txt")
# → {"status": "error", "error": "delete_file is destructive. Set force=True to confirm."}

# Success
file(action="delete_file", path="tmp/old.txt", force=True)
```

#### `directory_tree` — Structured JSON

```python
file(action="directory_tree", path=".", max_depth=3,
     exclude_patterns=["__pycache__", "*.pyc", ".git"])
```

Returns:
```json
{
  "tree": [
    {"name": "src", "type": "directory", "children": [
      {"name": "main.py", "type": "file", "size": 1234}
    ]}
  ],
  "files": 1,
  "directories": 1
}
```

**Symlink cycle guard:** Detects and reports symlink cycles instead of infinite recursion.

**Known limitation:** `directory_tree` max_depth defaults to 5; very deep trees may be truncated.

#### `find_files` — Glob Pattern Matching

```python
file(action="find_files", pattern="**/*.py", path=".")
file(action="find_files", pattern="*.md", path="docs")
```

Returns up to 1000 results. Use `exclude_patterns` on `directory_tree` for broader filtering.

#### `append_file` — Append Without Reading

```python
file(action="append_file", path="logs/app.log", content="New log line\n")
```

Opens file in append mode. Creates file if not exists. No `.bak` garbage.

#### `search_files` — Full-Text Search

**Known limitation:** `search_files` index only covers `workspace_root`, not `agent_root`.

---

## 🔒 Security

### Path Resolution

All paths are resolved through `core.path_guard.resolve_path()` before any file operation:

| Path Type | Behavior |
|-----------|----------|
| **Relative** | Resolved against `default_root` ("agent" or "workspace") |
| **Absolute** | Allowed only if within `AGENT_ROOT` |
| **Traversal** (`../..`) | Blocked if resolves outside `AGENT_ROOT` |
| **Null bytes** | Blocked immediately |
| **Symlinks** | Followed via `Path.resolve()` — escapes caught by `_is_within()` |

**Protected files:** Infrastructure files (e.g., `core/config.py`) are read-allowed but write-blocked. The `WRITE_OPERATIONS` frozenset in `core/path_guard.py` controls which actions trigger the protected check. **v1.1 added `move_file`, `copy_file`, `create_directory` to this set.**

**v1.1 fix:** Destination paths for `move_file`/`copy_file`/`write_file` are checked for protection even when they don't exist yet. The resolved path tells us where the file would land.

### Safety Features

| Feature | Implementation |
|---------|---------------|
| **Path guard** | `resolve_path()` + `check_protected_file()` validates all paths |
| **Cancellation guard** | `ensure_not_cancelled(trace_id)` aborts before mutations |
| **Destructive actions** | `force=True` required for `delete_file`, `move_file`, `copy_file` |
| **Protected files** | `cfg.is_protected()` blocks edits to sensitive files |
| **Result compression** | `compress_result()` prevents MCP context overflow |
| **Null byte injection** | Blocked in `_safe_resolve()` |
| **Symlink cycles** | Detected in `directory_tree` with visited-path tracking |
| **Read size limits** | `read_file` rejects files >10MB; `read_media_file` rejects >5MB (default) |

---

## 📤 Output

All actions return standardized `dict` via `compress_result()`.

*(Fill this section with relevant info from edits and refactors. Add output format details as they are learned.)*

---

*Last updated: 2026-07-03. See [ARCHITECTURE.md](ARCHITECTURE.md) for file maps and design decisions, [CHANGELOG.md](CHANGELOG.md) for version history, [INSTRUCTIONS.md](INSTRUCTIONS.md) for AI editing rules.*
