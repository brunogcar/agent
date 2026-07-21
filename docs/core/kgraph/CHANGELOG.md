<- Back to [Knowledge Graph Overview](../KGRAPH.md)

# 🗺️ Changelog

## 📝 Version History

| Version | Date | Notes |
|---------|------|-------|
| **v1.4.1** | 2026-07-21 | **Understand Phase 1 hardening touched 5 kgraph files.** (1) `project.py` — `SKIP_DIRS` class constant consolidated (was duplicated in `discover_files.py` + `project.py`); added `.mypy_cache`, `.ruff_cache`, `.tox`, `htmlcov`, `.eggs`. (2) `tree_sitter_parser.py` — `extract_imports` + `extract_definitions_ts` accept optional `errors: list[str] \| None` param to surface syntax errors (was: silently swallowed). (3) `embeddings.py` — `extract_doc_chunks` now computes `line_start`/`line_end` by counting newlines (was: always 0,0); `embed_texts` empty-list short-circuit moved before availability check. (4) `vectors.py` — `get_project_vector_collection` signature changed from `(project_id: str)` to `(pm: ProjectManager)`; path is now project-scoped (`{project}/.understand/chroma/` for projects, `memory_root/understand/chroma/` for agent root — was: always `agent_root/.understand/chroma/`). (5) `queries.py` — `get_dependencies` + `get_callers` multi-language fix (was: hardcoded `.py`, silently dropped JS/TS/Go/Rust deps). |
| Pre-v1 | 2026-07-04 | Initial implementation. AST-based dependency extraction, SQLite graph storage, test targeting, project isolation. |
| **v1.1** | 2026-07-17 | **+11 languages + embedding performance.** (1) `LANGUAGE_MAP` expanded: Java, C, C++, Ruby, Lua, PHP, Scala, Swift, Kotlin. (2) `is_embedding_available()` — cached early-return check in `embeddings.py`. If LM Studio is down, all `embed_texts()` calls return None immediately (was: 965 × 30s timeouts). (3) Batched embedding in `parse_and_store.py` — 2-phase: parse → batch embed (100 per HTTP call). |
| **v1.0** | 2026-07-17 | **GraphStore.close_all() + atexit + AST cache key fix + roadmap cleanup.** (1) `GraphStore.close_all()` classmethod — closes ALL singleton instances + checkpoints WAL. Registered via `atexit` in `server.py` (was: no shutdown cleanup → potential WAL data loss on crash). (2) AST cache key fix — `parse_file_dependencies()` now uses the ORIGINAL `file_path` (may be relative) as the cache key, not the resolved absolute path. Cache hits survive project moves. (3) Roadmap cleanup — "Incremental indexing" marked ✅ Completed (already works via mtime+hash check in `discover_files.py`); "Fix yaml import" marked ✅ Completed (yaml IS available, was a false report). (4) understand v1.3.1: path resolve fix + ChromaDB path isolation (separate commits). |
| v1.3 update | 2026-07-13 | `tree_sitter_parser.py`: Added `DOC_EXTENSIONS` (.md/.txt/.rst), `ALL_SUPPORTED_EXTENSIONS`, `is_doc_file()`. `embeddings.py`: Added `extract_doc_chunks()` — chonkie sentence chunking for prose files. Doc chunks have `type: "doc"` metadata. Soft dependency on chonkie (fallback to single chunk). |

---

## ⚠️ Breaking Changes

#### v1.4.1 — 2026-07-21

| Change | Impact | Migration |
|--------|--------|-----------|
| `get_project_vector_collection` signature changed | Was `project_id: str`, now `pm: ProjectManager`. Path is now project-scoped. | Pass `pm` (the ProjectManager instance) instead of `project_id`. Internal callers updated. |
| `upsert_file_vectors` + `query_similar_code` signatures changed | Same: `project_id: str` → `pm: ProjectManager`. | Pass `pm` instead of `project_id`. |
| ChromaDB path moved for agent_root | Agent-root vectors now live at `memory_root/understand/chroma/` (was: `agent_root/.understand/chroma/`). | Delete the old `agent_root/.understand/chroma/` directory and re-run understand. We do NOT auto-migrate (would be a surprise move of multi-GB vector stores). |
| `extract_imports` + `extract_definitions_ts` new optional `errors` param | New keyword-only param. | No migration — defaults to `None` (old behavior). |

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
| Cross-language support | ✅ Done (v1.2+) — JavaScript, TypeScript, Go, Rust + 9 more languages (Java, C/C++, Ruby, Lua, PHP, Scala, Swift, Kotlin) via tree-sitter | — |
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

*Last updated: 2026-07-21 (v1.4.1). See [ARCHITECTURE.md](ARCHITECTURE.md) for file maps, [API.md](API.md) for component details, [INSTRUCTIONS.md](INSTRUCTIONS.md) for AI editing rules.*
