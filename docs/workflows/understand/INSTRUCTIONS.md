<- Back to [Understand Overview](../UNDERSTAND.md)

# 🛡️ AI Instructions

## ❌ NEVER DO

1. **Never use `async def` for nodes** — All nodes must be sync (`def`). LangGraph `StateGraph.add_node` expects sync functions. Use `asyncio.to_thread()` if async work is needed (but prefer sync APIs).
2. **Never hardcode `tid` strings** — Always use `state.get("trace_id", "")` for trace correlation.
3. **Never leave GraphStore connections open** — Always call `store.close()` in a `finally` block.
4. **Never use `read_bytes()` for large files** — Use `_chunked_md5()` for file hashing.
5. **Never create duplicate edges** — Deduplicate target paths with a `set` before `upsert_file_graph()`.
6. **Never use `ThreadPoolExecutor` + `new_event_loop()`** — Sync nodes don't need event loops. Use `graph.invoke()` directly.
7. **Never silently swallow exceptions** — Use `tracer.error()` to log failures, even in best-effort nodes like `node_report`.
8. **Never mutate `state` in-place** — Always return partial update `dict`s.
9. **Never create `.bak` files** — Forbidden by project rules.
10. **Never skip `compileall` before `pytest`** — Catches syntax errors early.
11. **Never let embedding failure crash the workflow** — [v1.1] `embed_texts()` returns `None` on failure; `upsert_file_vectors()` returns 0. Vector indexing is best-effort. Graph edges must still be stored. Use `tracer.warning`, not `tracer.error`.
12. **Never embed whole files when definitions exist** — [v1.1] Use `extract_definitions()` for per-function/class chunking. Whole-file embedding defeats semantic search (you can't find "the function that does X").

## ✅ ALWAYS DO

11. **Always pass `trace_id` to `_default_state()`** — Nodes need it for trace correlation.
12. **Always close GraphStore connections** — Use `try: ... finally: store.close()`.
13. **Always use `_chunked_md5()` for file hashing** — Prevents memory spikes.
14. **Always deduplicate target paths** — Use `set()` before `list()` for edge creation.
15. **Always treat `completed_with_errors` as success** — The workflow completed, just with some parse failures.
16. **Always log report generation failures** — Use `tracer.error()`, not bare `except: pass`.
17. **Always test sync node verification** — Assert `not inspect.iscoroutinefunction(node)`.
18. **Always update this doc** when adding nodes, changing parsing logic, or modifying storage.
19. **Always use `extract_definitions()` for chunking** — [v1.1] Per-definition (function/class/module) embeddings, not per-file or fixed-window. Richer semantic search.
20. **Always delete old vectors before upserting** — [v1.1] `upsert_file_vectors()` calls `collection.delete(where={"file_path": ...})` first, so renamed/deleted definitions don't leave stale vectors.
21. **Always batch embedding calls** — [v1.1] `embed_texts()` sends all texts in one HTTP request. Don't call it per-definition in a loop.

---

## 🚫 Anti-Patterns & Lessons Learned

> - **What happened:** All 4 nodes were `async def`, requiring a `ThreadPoolExecutor` + `new_event_loop()` sync facade. This was fragile, leaked threads, and bypassed `base.py`'s checkpoint/resume infrastructure.
> - **Why it matters:** Understand was the only workflow that didn't support checkpoint/resume. If it crashed mid-parse, the entire workflow had to restart from scratch. The event loop hack could hang under certain conditions.
> - **Fix:** Converted all nodes to sync (`def`). Routed through `base.py`'s standard `graph.invoke()`. Removed the `ThreadPoolExecutor` + `new_event_loop()` facade entirely. Used `_parse_dependencies_sync_from_string()` directly instead of the async `parse_file_dependencies()` wrapper.

> - **What happened:** All nodes used hardcoded `tid` strings (`"understand_init"`, `"understand_discover"`, `"understand_parse"`) instead of `state.get("trace_id")`. Trace correlation was impossible — JSONL logs couldn't link understand events back to the original user request.
> - **Why it matters:** Without trace correlation, debugging failed understand runs required grep-ing through all logs. The trace_id was created in `run_understand_workflow()` but never injected into state.
> - **Fix:** Added `trace_id` to `UnderstandState` TypedDict. `_default_state()` now accepts `trace_id` parameter. All nodes use `state.get("trace_id", "understand")` as fallback.

> - **What happened:** `GraphStore` was created in `node_init_project` but assigned to `_` (discarded). Later nodes created their own instances. No `.close()` was ever called — SQLite connections leaked until garbage collection.
> - **Why it matters:** Leaked connections can cause "database is locked" errors under concurrent access. WAL mode helps but doesn't eliminate the risk.
> - **Fix:** `node_init_project` now creates + closes GraphStore immediately (just verifying it works). `node_discover_files` and `node_parse_and_store` create their own instances and close them in `finally` blocks.

> - **What happened:** Edge creation added both `dep` and `dep.replace(".", "/") + ".py"` as target paths. When `dep` was already a path (e.g., `"models/user"`), this created duplicate edges.
> - **Why it matters:** Duplicate edges inflate the edge count and can cause redundant queries in impact analysis.
> - **Fix:** Target paths are collected in a `set()` before conversion to `list()`, eliminating duplicates.

> - **What happened:** [v1.1] ChromaDB vectors were never populated — `vectors.py` had `get_project_vector_collection()` but no code called it. The understand workflow built a graph (SQLite edges) but had no semantic search capability.
> - **Why it matters:** Without vectors, "find the function that does X" required exact import-path knowledge. Semantic search enables finding code by description, which is how developers actually think about code.
> - **Fix:** Added `extract_definitions()` (AST chunking into functions/classes/module) + `embed_texts()` (LM Studio `/v1/embeddings`) + `upsert_file_vectors()` (delete-then-insert into ChromaDB). `parse_and_store` calls all three after parsing each file. Graceful degradation: if LM Studio is down, vectors are skipped and the workflow completes with graph edges only.

---

*Last updated: 2026-07-06 (v1.1 — vector indexing). See [ARCHITECTURE.md](ARCHITECTURE.md) for file maps, [API.md](API.md) for node details, [CHANGELOG.md](CHANGELOG.md) for version history.*
