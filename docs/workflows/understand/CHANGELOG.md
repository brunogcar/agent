<- Back to [Understand Overview](../UNDERSTAND.md)

# 🗺️ Changelog

## 📝 Version History

| Version | Date | Changes |
|---------|------|---------|
| v1.0 | 2026-07-05 | **Architecture conversion:** All nodes converted from `async def` to `def` (sync). Routed through `base.py`'s standard `graph.invoke()` — gives understand checkpoint/resume support and trace_id propagation like all other workflows. Removed dangerous `ThreadPoolExecutor` + `new_event_loop()` sync facade. Fixed 16 bugs: trace_id propagation (#1/#2), GraphStore lifecycle (#3/#4/#15), os.walk mutation (#5), chunked MD5 (#6), duplicate edges (#7), CPU-bound blocking (#8 — auto-fixed by sync conversion), completed_with_errors (#9), silent report exception (#11), nested event loop (#12 — auto-fixed), return type annotation (#13), configurable batch size (#17). |

---

## ⚠️ Breaking Changes

### v1.0 — 2026-07-05

| Change | Impact | Migration |
|--------|--------|-----------|
| All nodes converted from `async def` to `def` | Nodes are now sync. `graph.ainvoke()` no longer works — use `graph.invoke()`. | No migration — `base.py` already uses `graph.invoke()`. |
| `run_understand_workflow()` (async) removed | Was the async orchestrator. Replaced by `run_understand_workflow_sync()` which now calls `graph.invoke()` directly. | Use `run_understand_workflow_sync()` or route through `base.py`'s `run_workflow()`. |
| `ThreadPoolExecutor` + `new_event_loop()` removed | The sync facade no longer creates threads or event loops. | No migration — callers see the same sync API. |
| `trace_id` added to `UnderstandState` | State now includes `trace_id` field. Nodes use it for trace correlation. | No migration — `base.py` injects it automatically. |
| `_default_state()` accepts `trace_id` parameter | New optional parameter. | No migration — defaults to `""`. |
| New env var: `UNDERSTAND_BATCH_SIZE` | Configurable batch size for AST parsing. Default: 10. | Optional — add to `.env` to customize. |

---

## ✅ Completed

| Feature | Status | Notes |
|---------|--------|-------|
| Project initialization | ✅ v1.0 | ProjectManager resolution, GraphStore creation (with error handling) |
| File discovery | ✅ v1.0 | os.walk with filtered dirs, chunked MD5 hash check |
| AST parsing | ✅ v1.0 | Sync _parse_dependencies_sync_from_string — no event loop blocking |
| Graph storage | ✅ v1.0 | GraphStore upsert with proper connection lifecycle (open → use → close) |
| Incremental updates | ✅ v1.0 | MD5 hash comparison, only re-parse changed files |
| Batch processing | ✅ v1.0 | Configurable batch size via UNDERSTAND_BATCH_SIZE env var |
| Report generation | ✅ v1.0 | Structured report with error logging (was silent) |
| Trace correlation | ✅ v1.0 | trace_id propagated through state to all nodes |
| Checkpoint/resume support | ✅ v1.0 | Routed through base.py's standard graph.invoke() path |
| Sync nodes (no event loop) | ✅ v1.0 | All nodes are def (sync) — consistent with other workflows |

---

## 🔄 In Progress / Next Up

| # | Feature | Notes | Priority |
|---|---------|-------|----------|
| 1 | **Configurable `skip_dirs`** | Currently hardcoded local set. Should be `.env` or `ProjectManager` config. | P3 |
| 2 | **Test restructure** | Split `test_understand.py` into per-node files + `conftest.py` | P1 |
| 3 | **ChromaDB vector indexing** | Currently GraphStore creates schema but vectors are not populated | P2 |
| 4 | **Multi-language support** | Support JavaScript, TypeScript, Go, etc. | P3 |

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

*Last updated: 2026-07-05. See [ARCHITECTURE.md](ARCHITECTURE.md) for file maps, [API.md](API.md) for node details, [INSTRUCTIONS.md](INSTRUCTIONS.md) for AI editing rules.*
