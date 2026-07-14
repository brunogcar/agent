<- Back to [Understand Overview](../UNDERSTAND.md)

# 🗺️ Changelog

## ✅ Completed

### 📝 Version History

| Version | Date | Summary |
|---------|------|---------|
| v1.3 | 2026-07-13 | **Doc indexing (.md/.txt/.rst).** `discover_files` now finds doc files alongside code. `parse_and_store` branches: code → tree-sitter; docs → chonkie sentence chunking. New `extract_doc_chunks()` in `embeddings.py`. Chonkie is a soft dependency. |
| v1.2.1 | 2026-07-13 | **Bugfix + doc drift.** P1: `parse_and_store` `store.close()` wrapped in `finally` (was leaking SQLite connection). P2: WORKFLOW_METADATA version "1.0" → "1.2". UNDERSTAND.md rewritten — was describing Pre-v1.0 architecture. |
| v1.2 | 2026-07-06 | **Multi-language support (tree-sitter).** Tree-sitter replaces `ast` parser. Supports Python, JavaScript/TypeScript, Go, Rust through one unified API. |
| v1.1 | 2026-07-06 | **ChromaDB vector indexing (#3).** Per-definition code embeddings (functions, classes, module docstrings) via LM Studio `/v1/embeddings`. Graceful degradation when LM Studio is down. |
| v1.0 | 2026-07-05 | **Subpackage split.** Split monolithic `workflows/understand.py` (326 lines) into `workflows/understand_impl/` subpackage. Added `WORKFLOW_METADATA`. Fixed 16 bugs. |
| Pre-v1.0 | 2026-07-05 | **Architecture conversion (pre-split).** All nodes converted from `async def` to `def` (sync). Routed through `base.py`'s standard `graph.invoke()`. Fixed 16 bugs: trace_id propagation, GraphStore lifecycle, os.walk mutation, chunked MD5, duplicate edges, etc. |

---

### ⚠️ Breaking Changes

#### v1.2 — 2026-07-06

| Change | Impact | Migration |
|--------|--------|-----------|
| Tree-sitter replaces `ast` parser | Multi-language support (Python, JS/TS, Go, Rust). `ast`-specific behavior no longer available. | No migration — tree-sitter is a superset. If external code imported `ast`-based parsing, switch to `tree_sitter_parser.py`. |

#### v1.0 — 2026-07-05

| Change | Impact | Migration |
|--------|--------|-----------|
| All nodes converted from `async def` to `def` | Nodes are now sync. `graph.ainvoke()` no longer works — use `graph.invoke()`. | No migration — `base.py` already uses `graph.invoke()`. |
| `run_understand_workflow()` (async) removed | Was the async orchestrator. Replaced by `run_understand_workflow_sync()`. | Use `run_understand_workflow_sync()` or route through `base.py`'s `run_workflow()`. |
| `ThreadPoolExecutor` + `new_event_loop()` removed | The sync facade no longer creates threads or event loops. | No migration — callers see the same sync API. |
| `trace_id` added to `UnderstandState` | State now includes `trace_id` field. | No migration — `base.py` injects it automatically. |
| `_default_state()` accepts `trace_id` parameter | New optional parameter. | No migration — defaults to `""`. |
| New env var: `UNDERSTAND_BATCH_SIZE` | Configurable batch size for AST parsing. Default: 10. | Optional — add to `.env` to customize. |

---

## 🔄 In Progress / Next Up

| # | Feature | Notes | Priority |
|---|---------|-------|----------|
| 1 | **Configurable `skip_dirs`** | Currently hardcoded local set. Should be `.env` or `ProjectManager` config. | P3 |
| 5 | **Additional languages** | Java, C/C++, Ruby via tree-sitter (tree-sitter-languages already bundles these — just add to LANGUAGE_MAP). | P3 |

---

## 🚫 Deferred / Out of Scope

| # | Feature | Why Deferred | Priority |
|---|---------|--------------|----------|
| 1 | **Remove GraphStore** | GraphStore is essential for dependency querying. Removing it would break impact analysis. | Skip |
| 2 | **Remove incremental updates** | Full re-parse on every run would be too slow for large projects. | Skip |
| 3 | **Remove batch processing** | Processing all files at once would cause memory spikes. | Skip |
| 4 | **Real-time file watching** | File watching would require additional infrastructure (e.g., watchdog). | Skip |
| 5 | **IDE integration** | IDE plugins would require LSP or VS Code extension development. | Skip |

---

*Last updated: 2026-07-13 (v1.3). See [ARCHITECTURE.md](ARCHITECTURE.md) for file maps, [API.md](API.md) for node details, [INSTRUCTIONS.md](INSTRUCTIONS.md) for AI editing rules.*
