<- Back to [Knowledge Graph Overview](../KGRAPH.md)

# 🗺️ Changelog

## 📝 Version History

| Version | Date | Notes |
|---------|------|-------|
| Pre-v1 | 2026-07-04 | Initial implementation. AST-based dependency extraction, SQLite graph storage, test targeting, project isolation. |
| **v1.0** | 2026-07-17 | **GraphStore.close_all() + atexit + AST cache key fix + roadmap cleanup.** (1) `GraphStore.close_all()` classmethod — closes ALL singleton instances + checkpoints WAL. Registered via `atexit` in `server.py` (was: no shutdown cleanup → potential WAL data loss on crash). (2) AST cache key fix — `parse_file_dependencies()` now uses the ORIGINAL `file_path` (may be relative) as the cache key, not the resolved absolute path. Cache hits survive project moves. (3) Roadmap cleanup — "Incremental indexing" marked ✅ Completed (already works via mtime+hash check in `discover_files.py`); "Fix yaml import" marked ✅ Completed (yaml IS available, was a false report). (4) understand v1.3.1: path resolve fix + ChromaDB path isolation (separate commits). |
| v1.3 update | 2026-07-13 | `tree_sitter_parser.py`: Added `DOC_EXTENSIONS` (.md/.txt/.rst), `ALL_SUPPORTED_EXTENSIONS`, `is_doc_file()`. `embeddings.py`: Added `extract_doc_chunks()` — chonkie sentence chunking for prose files. Doc chunks have `type: "doc"` metadata. Soft dependency on chonkie (fallback to single chunk). |

---

## ⚠️ Breaking Changes

*(No breaking changes yet. Add entries here when versions are released.)*

---

## ✅ Completed

| Feature | Status | Notes |
|---------|--------|-------|
| AST-based dependency extraction | ✅ Pre-v1 | Deterministic `ast` module import parsing |
| SQLite graph storage | ✅ Pre-v1 | WAL mode, thread-safe, indexed |
| Test targeting | ✅ Pre-v1 | Source → test file mapping via AST analysis |
| Hybrid validation | ✅ Pre-v1 | mtime + size (fast) then MD5 (slow) cache invalidation |
| Project isolation | ✅ Pre-v1 | Per-project `.understand/` directories |
| Critical path detection | ✅ Pre-v1 | Full suite trigger for global infrastructure files |
| Project-specific ChromaDB collections | ✅ Pre-v1 | Physical isolation from main memory |

---

## 🔄 In Progress / Next Up

| Feature | Notes | Priority |
|---------|-------|----------|
| Class/function-level nodes | Beyond file-level granularity | P2 |
| Cross-language support | JavaScript, TypeScript AST parsing | P3 |
| Call graph analysis | Function-level dependency tracking | P2 |
| Incremental indexing | ✅ v1.0 — Already works (mtime + file_size + content_hash check in `discover_files.py`) | — |
| Visualization | Mermaid/SVG export of dependency graphs | P3 |
| Test coverage integration | Map coverage data to graph nodes | P3 |
| Fix `yaml` import in `test_mapper.py` | ✅ v1.0 — Not a bug (yaml IS available; PyYAML is in requirements.txt). The real issue was `tree_sitter_languages` not installed. | — |
| GraphStore cleanup on shutdown | ✅ v1.0 — `close_all()` classmethod + `atexit` registration in `server.py` | — |
| Relative path in AST cache key | ✅ v1.0 — `parse_file_dependencies()` uses original `file_path` (not resolved) as cache key | — |

---

## 🚫 Deferred / Out of Scope

*(No deferred items yet. Add entries here as decisions are made.)*

---

*Last updated: 2026-07-13 (v1.3 update). See [ARCHITECTURE.md](ARCHITECTURE.md) for file maps, [API.md](API.md) for component details, [INSTRUCTIONS.md](INSTRUCTIONS.md) for AI editing rules.*
