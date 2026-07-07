<- Back to [File Overview](../FILE.md)

# 🗺️ Changelog

## 📝 Version History

| Version | Date | Notes |
|---------|------|-------|
| v1.2 | 2026-07-08 | chonkie chunking (read_file, read_multiple_files), count_lines action, UTF-8→cp1252→latin-1 encoding fallback, read_file/read_multiple_files line-count fix (splitlines), `count_lines` added to path_guard READ_OPERATIONS, `chonkie>=1.0` pinned |
| v1.1 | — | Path guard integration, new actions (copy_file, append_file, find_files, read_media_file size limit, read_file size limit, directory_tree cycle guard) |
| v1.0 | — | Initial atomic action refactor: thin facade + @meta_tool + atomic action modules |

---

## ⚠️ Breaking Changes

### v1.0 → v1.1

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

### v1.2 (non-breaking additions)
- **New action: `count_lines`** — wc -l equivalent, 64KB binary chunk reads, O(1) memory
- **New params on `read_file` / `read_multiple_files`:** `chunk` (bool), `chunk_method` ("token"|"sentence"), `chunk_size` (int, default 512)
- **Encoding fallback chain** in `read_file` / `read_multiple_files`: UTF-8 (strict) → cp1252 (strict) → latin-1 (never fails). The encoding that succeeded is reported in the result `encoding` field. Backward compatible — old callers that didn't read this field are unaffected.
- **`core/path_guard.py`**: added `count_lines` to `READ_OPERATIONS` (was missing — new action)
- **Soft dependency on `chonkie`**: only imported inside the chunking branch; non-chunk reads and all other file actions work fine without it
- **Fixed `read_file` / `read_multiple_files` `lines` field**: now uses `splitlines()` (was `count("\n")+1`, which overcounted files ending in a trailing newline by 1 — e.g. `"a\nb\nc\n"` reported 4 instead of 3)
- **Pinned `chonkie>=1.0`** in requirements.txt (was unpinned — reproducibility risk)
- No existing params were removed or renamed — v1.1 callers are unaffected

---

## ✅ Completed

| Feature | Status | Notes |
|---------|--------|-------|
| chonkie chunking (`read_file`, `read_multiple_files`) | ✅ v1.2 | Token + Sentence chunkers, soft dep (lazy import) |
| Encoding fallback chain | ✅ v1.2 | UTF-8 → cp1252 → latin-1; encoding reported in result |
| `count_lines` / wc | ✅ v1.2 | 64KB binary chunks, O(1) memory, encoding-independent |
| `lines` field correctness (`read_file`, `read_multiple_files`) | ✅ v1.2 | `splitlines()` replaces `count("\n")+1` (overcounted trailing-newline files by 1) |
| `chonkie` pinned | ✅ v1.2 | `chonkie>=1.0` in requirements.txt (was unpinned) |
| `copy_file` | ✅ v1.1 | Copy file or directory with force overwrite |
| `append_file` | ✅ v1.1 | Append content without reading full file |
| `find_files` | ✅ v1.1 | Glob pattern matching (`**/*.py`), max 1000 results |
| `read_media_file` size limit | ✅ v1.1 | `max_bytes` param, default 5MB |
| `read_file` size limit | ✅ v1.1 | 10MB hard ceiling |
| `directory_tree` cycle guard | ✅ v1.1 | Symlink cycle detection |
| `path_guard` action names | ✅ v1.1 | `READ_OPERATIONS`/`WRITE_OPERATIONS` updated for new action names |
| Un-multiplex file tool | ✅ v1.0 | Thin facade + @meta_tool + atomic action modules |
| SQLite FTS search | ✅ v1.0 | `search_files` via SQLite FTS index |
| Cancellation guard | ✅ v1.0 | `ensure_not_cancelled(trace_id)` before mutations |
| Result compression | ✅ v1.0 | `compress_result()` prevents MCP context overflow |
| Protected file enforcement | ✅ v1.0 | `cfg.is_protected()` blocks edits to sensitive files |

---

## 🔄 In Progress / Next Up

| Feature | Notes | Priority |
|---------|-------|----------|
| `file_hash` (SHA256/MD5) | Artifact verification | P2 |
| `search_content` (grep-like) | Fast content search without FTS index | P2 |
| `get_disk_usage` | Workspace size management | P2 |
| `touch` | Create empty file or update timestamp | P2 |
| Semantic chunking via LM Studio embeddings | Add to `read_file`/`read_multiple_files` as `chunk_method="semantic"`; depends on LM Studio `/v1/embeddings` availability — needs design decision on offline fallback | P3 |

---

## 🚫 Deferred / Out of Scope

| # | Feature | Why Deferred | Priority |
|---|---------|------------|----------|
| 1 | `watch_file` | File change detection (deferred) | P3 |
| 2 | Memory tool chunking | Next phase after file tool v1.2 — same chonkie integration but in `tools/memory_ops/` | P1 (next phase) |
| 3 | Workflow integration (autocode context summarization #37, understand `.md` files, research `_trim_context`) | Later phases — chonkie available once memory tool integration lands | P2 |

---

*Last updated: 2026-07-08. See [ARCHITECTURE.md](ARCHITECTURE.md) for file maps, [API.md](API.md) for action details, [INSTRUCTIONS.md](INSTRUCTIONS.md) for AI editing rules.*
