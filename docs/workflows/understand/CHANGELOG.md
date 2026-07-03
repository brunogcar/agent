<- Back to [Understand Overview](../UNDERSTAND.md)

# 🗺️ Changelog

## 📝 Version History

| Version | Date | Changes |
|---------|------|---------|

*(Fill this section with relevant info from edits and refactors. Add version history as it is learned.)*

---

## ⚠️ Breaking Changes

*(No breaking changes yet. This is a pre-v1 document. Add breaking changes here when they occur.)*

---

## 📝 Version History

| Version | Date | Changes |
|---------|------|---------|

*(Fill this section with relevant info from edits and refactors. Add version history as it is learned.)*

---

## ✅ Completed

| Feature | Status | Notes |
|---------|--------|-------|
| Project initialization | ✅ Pre-v1.0 | ProjectManager resolution, GraphStore creation |
| File discovery | ✅ Pre-v1.0 | os.walk with skip directories, MD5 hash check |
| AST parsing | ✅ Pre-v1.0 | parse_file_dependencies for import extraction |
| Graph storage | ✅ Pre-v1.0 | GraphStore upsert for file nodes and dependency edges |
| Incremental updates | ✅ Pre-v1.0 | MD5 hash comparison, only re-parse changed files |
| Batch processing | ✅ Pre-v1.0 | Batch size 10 for memory efficiency |
| Report generation | ✅ Pre-v1.0 | Structured report with analysis results |
| Memory storage | ✅ Pre-v1.0 | Project metadata in procedural memory |

---

## 🔄 In Progress / Next Up

| # | Feature | Notes | Priority |
|---|---------|-------|----------|
| 1 | **Fix hardcoded `tid` strings in all nodes** | All nodes use hardcoded `tid` (`"understand_init"`, `"understand_discover"`, etc.) instead of `state.get("trace_id", "")`. No trace correlation. | P0 |
| 2 | **Fix `_default_state` missing `trace_id`** | `trace_id` created in `run_understand_workflow()` but never injected into `initial_state`. Nodes can't access it. | P0 |
| 3 | **Fix `GraphStore` created but discarded in `node_init`** | `GraphStore` instance created but not stored in state. Later nodes create their own. Wasteful and risky. | P0 |
| 4 | **Fix `GraphStore` connection leaked in `node_discover`** | No `with` statement or explicit `.close()`. SQLite connections left open until GC. | P1 |
| 5 | **Fix `os.walk` dirs mutation fragility** | `dirs[:] = [d for d in dirs if d not in skip_dirs]` mutates in-place. Fragile if `os.walk` implementation changes. | P1 |
| 6 | **Fix double file read for MD5** | `read_bytes()` reads entire file into memory. Should use chunked hashing. | P1 |
| 7 | **Fix duplicate target paths in edge creation** | Both `dep.replace(".", "/") + ".py"` and `dep` added as targets. Duplicate edges. | P1 |
| 8 | **Fix CPU-bound AST parsing without `to_thread()`** | `parse_file_dependencies` is CPU-bound. `asyncio.gather` blocks event loop. | P1 |
| 9 | **Fix `completed_with_errors` treated as failure** | `run_understand_workflow()` checks `status == "completed"` only. `"completed_with_errors"` treated as failure. | P1 |
| 10 | **Fix `report_tool` signature** | Verify `report()` tool signature matches usage. | P1 |
| 11 | **Fix silent exception in `node_report`** | `try/except` around `report_tool()` with no logging. Silent failures. | P2 |
| 12 | **Fix dangerous nested event loop in sync facade** | `ThreadPoolExecutor` + `new_event_loop()` may leak threads or hang. | P2 |
| 13 | **Fix wrong return type on `build_understand_graph`** | Returns `CompiledGraph` but annotated as `StateGraph`. | P2 |
| 14 | **Make `skip_dirs` configurable** | Currently hardcoded local set. Should be `.env` or `ProjectManager` config. | P3 |
| 15 | **Add `GraphStore` init failure handling** | `node_init_project` doesn't handle `GraphStore.__init__` failure. | P3 |
| 16 | **Test restructure** | Split `test_understand.py` into per-node files + `conftest.py` | P1 |
| 17 | **Configurable batch size** | Make `UNDERSTAND_BATCH_SIZE` actually used in code | P2 |
| 18 | **ChromaDB vector indexing** | Currently GraphStore creates schema but vectors are not populated | P2 |
| 19 | **Multi-language support** | Support JavaScript, TypeScript, Go, etc. | P3 |

---

## 🚫 Deferred / Out of Scope

| # | Feature | Why Deferred | Priority |
|---|---------|------------|----------|
| 1 | **Remove GraphStore** | GraphStore is essential for dependency querying. Removing it would break impact analysis. | Skip |
| 2 | **Remove incremental updates** | Full re-parse on every run would be too slow for large projects. | Skip |
| 3 | **Remove batch processing** | Processing all files at once would cause memory spikes. | Skip |
| 4 | **Real-time file watching** | File watching would require additional infrastructure (e.g., watchdog). Out of scope. | Skip |
| 5 | **IDE integration** | IDE plugins would require LSP or VS Code extension development. Out of scope. | Skip |

---

*Last updated: 2026-07-03. See [ARCHITECTURE.md](ARCHITECTURE.md) for file maps, [API.md](API.md) for node reference, [INSTRUCTIONS.md](INSTRUCTIONS.md) for AI editing rules.*
