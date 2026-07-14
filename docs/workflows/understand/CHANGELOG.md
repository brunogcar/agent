<- Back to [Understand Overview](../UNDERSTAND.md)

# 🗺️ Changelog

## 📝 Version History

| Version | Date | Changes |
|---------|------|---------|
| v1.2.1 | 2026-07-13 | **Bugfix + doc drift:** P1: `parse_and_store` `store.close()` wrapped in `finally` (was outside — leaked SQLite connection on batch-level exception). P2: WORKFLOW_METADATA version "1.0" → "1.2". UNDERSTAND.md rewritten — was describing Pre-v1.0 architecture (async, Python AST only, memory integration that doesn't exist, "not a LangGraph StateGraph"). Now reflects v1.2 reality (sync, tree-sitter multi-language, LangGraph StateGraph, ChromaDB vectors). ARCHITECTURE.md documents completion pattern (status set by parse_and_store, not node_done). INSTRUCTIONS.md numbering fixed (#11 duplication). |
| v1.1 | 2026-07-06 | **ChromaDB vector indexing (#3):** `parse_and_store` now populates per-definition code embeddings (functions, classes, module docstrings) in ChromaDB for semantic search. Uses LM Studio's `/v1/embeddings` endpoint (OpenAI-compatible) with GGUF embedding models. Graceful degradation: if LM Studio is unavailable, vector indexing is skipped and the workflow completes with graph edges only. New modules: `core/kgraph/embeddings.py` (AST chunking + embedding client), `core/kgraph/vectors.py` (upsert + query). New config: `EMBEDDING_MODEL`, `EMBEDDING_BASE_URL`, `EMBEDDING_ENABLED`. Also marked #2 (test restructure) as completed. |
| v1.0 | 2026-07-05 | **Subpackage split:** Split monolithic `workflows/understand.py` (326 lines) into `workflows/understand_impl/` subpackage with per-node modules. Added `WORKFLOW_METADATA` for MCP client introspection. Thin facade re-exports `build_understand_graph`, `_default_state`, `WORKFLOW_METADATA`, `run_understand_workflow_sync`. Tests split into per-node files (`test_graph`, `test_state`, `test_init_project`, `test_helpers`) + `conftest.py`. |
| Pre-v1.0 | 2026-07-05 | **Architecture conversion (pre-split):** All nodes converted from `async def` to `def` (sync). Routed through `base.py`'s standard `graph.invoke()` — gives understand checkpoint/resume support and trace_id propagation like all other workflows. Removed dangerous `ThreadPoolExecutor` + `new_event_loop()` sync facade. Fixed 16 bugs: trace_id propagation (#1/#2), GraphStore lifecycle (#3/#4/#15), os.walk mutation (#5), chunked MD5 (#6), duplicate edges (#7), CPU-bound blocking (#8 — auto-fixed by sync conversion), completed_with_errors (#9), silent report exception (#11), nested event loop (#12 — auto-fixed), return type annotation (#13), configurable batch size (#17). |

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
| Test restructure | ✅ v1.0 | Per-node test files + conftest.py (done in v1.0 split) |
| ChromaDB vector indexing | ✅ v1.1 | Per-definition embeddings via LM Studio `/v1/embeddings`. AST chunking (functions, classes, module docstrings). Graceful degradation when LM Studio is down. Semantic search via `query_similar_code()`. |
| Multi-language support | ✅ v1.2 | Tree-sitter replaces `ast` parser. Supports Python, JavaScript/TypeScript, Go, Rust through one unified API. `discover_files` finds all supported extensions; `parse_and_store` detects language per file. |

---

## 🔄 In Progress / Next Up

| # | Feature | Notes | Priority |
|---|---------|-------|----------|
| 1 | **Configurable `skip_dirs`** | Currently hardcoded local set. Should be `.env` or `ProjectManager` config. | P3 |
| 5 | **Additional languages** | Java, C/C++, Ruby via tree-sitter (tree-sitter-languages already bundles these — just add to LANGUAGE_MAP). | P3 |
| 6 | **Chonkie chunking for `.md`/`.txt` docs (conditional)** | **When** understand is extended to index `.md`/`.txt`/`.rst` docs (currently code-only), use chonkie `SentenceChunker` for those file types. Tree-sitter (currently used for code definitions) can't parse prose — chonkie sentence chunking is the right tool for docs. Reuses `_chunk_text()` from `tools/file_ops/actions/read_file.py` (file tool v1.2 integration). This is **conditional** on file-type support landing first — not a standalone task. See `docs/TOOLS.md` § "Chunking (chonkie)". | P2 |

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

*Last updated: 2026-07-13 (v1.2.1). See [ARCHITECTURE.md](ARCHITECTURE.md) for file maps, [API.md](API.md) for node details, [INSTRUCTIONS.md](INSTRUCTIONS.md) for AI editing rules.*
