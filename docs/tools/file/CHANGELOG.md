<- Back to [File Overview](../FILE.md)

# 🗺️ Changelog

## 📝 Version History

| Version | Date | Notes |
|---------|------|-------|
| v1.1 | — | Path guard integration, new actions (copy_file, append_file, find_files, read_media_file size limit, read_file size limit, directory_tree cycle guard) |
| v1 | — | Initial atomic action refactor: thin facade + @meta_tool + atomic action modules |

---

## ⚠️ Breaking Changes

### v1 → v1.1

| Old Action | New Action | Migration |
|------------|-----------|-----------|
| `read` | `read_file` | `file(action="read_file", ...)` |
| `write` | `write_file` | `file(action="write_file", ...)` |
| `list` | `list_directory` | `file(action="list_directory", ...)` |
| `search` | `search_files` | `file(action="search_files", ...)` |
| `patch` | `patch_file` | `file(action="patch_file", ...)` |
| `backup` | `backup_file` | `file(action="backup_file", ...)` |
| `read_many` | `read_multiple_files` | `file(action="read_multiple_files", ...)` |
| `mode` param | Removed | Use `max_chars`, `head`, or `tail` |

### v1.1 (path_guard integration)
- Replaced custom `_resolve()` in `helpers.py` with thin wrapper around `core.path_guard.resolve_path`
- Updated `write_file`, `append_file`, `edit_file`, `patch_file` handlers to use `check_protected_file()` instead of direct `cfg.is_protected()`
- Added `move_file`, `copy_file`, `create_directory` to `WRITE_OPERATIONS` in `core/path_guard.py`
- Fixed facade destination protected check to run even when destination doesn't exist yet
- Added `list_allowed_directories` to `READ_OPERATIONS`
- Added `test_file_path_guard_integration.py` to prevent regression

---

## ✅ Completed

| Feature | Status | Notes |
|---------|--------|-------|
| `copy_file` | ✅ v1.1 | Copy file or directory with force overwrite |
| `append_file` | ✅ v1.1 | Append content without reading full file |
| `find_files` | ✅ v1.1 | Glob pattern matching (`**/*.py`), max 1000 results |
| `read_media_file` size limit | ✅ v1.1 | `max_bytes` param, default 5MB |
| `read_file` size limit | ✅ v1.1 | 10MB hard ceiling |
| `directory_tree` cycle guard | ✅ v1.1 | Symlink cycle detection |
| `path_guard` action names | ✅ v1.1 | `READ_OPERATIONS`/`WRITE_OPERATIONS` updated for new action names |
| Un-multiplex file tool | ✅ v1 | Thin facade + @meta_tool + atomic action modules |
| SQLite FTS search | ✅ v1 | `search_files` via SQLite FTS index |
| Cancellation guard | ✅ v1 | `ensure_not_cancelled(trace_id)` before mutations |
| Result compression | ✅ v1 | `compress_result()` prevents MCP context overflow |
| Protected file enforcement | ✅ v1 | `cfg.is_protected()` blocks edits to sensitive files |

---

## 🔄 In Progress / Next Up

| Feature | Notes | Priority |
|---------|-------|----------|
| `read_file` / `write_file` encoding | Support cp1252, latin-1, etc. | P2 |
| `file_hash` (SHA256/MD5) | Artifact verification | P2 |
| `search_content` (grep-like) | Fast content search without FTS index | P2 |
| `count_lines` / `wc` | Fast stats without reading full file | P2 |
| `get_disk_usage` | Workspace size management | P2 |
| `touch` | Create empty file or update timestamp | P2 |

---

## 🚫 Deferred / Out of Scope

| # | Feature | Why Deferred | Priority |
|---|---------|------------|----------|
| 1 | `watch_file` | File change detection (deferred) | P3 |

---

*Last updated: 2026-07-03. See [ARCHITECTURE.md](ARCHITECTURE.md) for file maps, [API.md](API.md) for action details, [INSTRUCTIONS.md](INSTRUCTIONS.md) for AI editing rules.*
