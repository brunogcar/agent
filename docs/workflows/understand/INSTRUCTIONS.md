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
12. **Never embed whole files when definitions exist** — [v1.1] Use `extract_definitions()` for per-function/class chunking. Whole-file embedding defeats semantic search.
13. **Never use tree-sitter for doc files** — [v1.3] `.md`/`.txt`/`.rst` files use chonkie `extract_doc_chunks()`, not tree-sitter `extract_definitions()`. Tree-sitter can't parse prose. Use `is_doc_file()` to branch.
14. **[v1.4.1 P1-7] Never create GraphStore outside `try`** — The `GraphStore(db_path)` constructor CAN raise (SQLite locked, disk full, corrupt WAL). If it's outside `try`, the `finally: store.close()` raises `NameError` (store is undefined), masking the original exception. Always: `store = None` before `try`; `if store is not None: store.close()` in `finally`.
15. **[v1.4.1 P1-6] Never ignore cancellation in long loops** — The base.py 600s daemon-thread timeout doesn't kill the thread (Python limitation). Without cooperative `is_workflow_cancelled()` checks, a cancelled understand workflow keeps running in the background, wasting CPU + disk I/O. Always poll `is_workflow_cancelled(trace_id)` at loop boundaries (every 10-100 files, every batch).
16. **[v1.4.1 P1-3] Never hardcode the agent_root ChromaDB path for all projects** — The vector path must be project-scoped (`{project}/.understand/chroma/` for projects, `memory_db/understand/chroma/` for agent root). Hardcoding `agent_root/.understand/chroma/` orphans vectors when a project's `.understand/` is deleted.
17. **[v1.4.1 P2-12] Never claim "checkpoint/resume" without verifying** — Understand does NOT save node-level mid-execution checkpoints (nodes use `tracer.step` directly, not `node_step(checkpoint=True)`). Checkpoints ARE saved on crash/cancel/timeout by base.py's exception handler. Don't claim more than what's actually implemented.

## ✅ ALWAYS DO

18. **Always pass `trace_id` to `_default_state()`** — Nodes need it for trace correlation.
19. **Always close GraphStore connections** — Use `try: ... finally: if store is not None: store.close()`.
20. **Always use `_chunked_md5()` for file hashing** — Prevents memory spikes.
21. **Always deduplicate target paths** — Use `set()` before `list()` for edge creation.
22. **Always treat `completed_with_errors` as success** — The workflow completed, just with some parse failures.
23. **Always log report generation failures** — Use `tracer.error()`, not bare `except: pass`.
24. **Always test sync node verification** — Assert `not inspect.iscoroutinefunction(node)`.
25. **Always update this doc** when adding nodes, changing parsing logic, or modifying storage.
26. **Always use `extract_definitions()` for chunking** — [v1.1] Per-definition (function/class/module) embeddings, not per-file or fixed-window.
27. **Always delete old vectors before upserting** — [v1.1] `upsert_file_vectors()` calls `collection.delete(where={"file_path": ...})` first.
28. **Always batch embedding calls** — [v1.1] `embed_texts()` sends all texts in one HTTP request. Don't call it per-definition in a loop.
29. **[v1.4.1 P1-1] Always bail on `status == "failed"`** — At the top of every node: `if state.get("status") == "failed": return {}`. Belt-and-suspenders alongside `route_after_init` — if a future graph refactor adds a direct edge past a failed node, the node itself short-circuits.
30. **[v1.4.1 P1-6] Always check `is_workflow_cancelled()` in loops** — At loop entry + every 10-100 iterations + every batch. Return `{"status": "failed", "errors": ["Workflow cancelled"]}` on cancel.
31. **[v1.4.1 P2-10] Always cap the errors list at 100** — Use `_append_capped(errors, msg, _ERRORS_CAP)`. A final `"... and N more errors (capped at 100)"` entry preserves the count for the operator.
32. **[v1.4.1 P3-1] Always re-check file size before `read_text`** — A file can grow between discover and parse (especially on long-running invocations). `if full_path.stat().st_size > ProjectManager.MAX_FILE_SIZE_BYTES: skip + append error`.
33. **[v1.4.1 P3-4] Always pass `errors=errors` to `extract_imports` + `extract_definitions_ts`** — Lets tree-sitter parse failures surface instead of being silently swallowed.
34. **[v1.4.1 P2-2] Always use `ProjectManager.SKIP_DIRS`** — Don't define a local `skip_dirs` set in nodes. The class constant is the single source of truth (adding a new dir is a one-line change).
35. **[v1.4.1 P0-2] Always lazy-import kgraph in the facade** — `from core.kgraph.project import is_same_path` inside the function, not at module top-level. A broken kgraph shouldn't cascade to every caller of `workflows.understand`.

---

## 🚫 Anti-Patterns & Lessons Learned

> - **What happened:** All 4 nodes were `async def`, requiring a `ThreadPoolExecutor` + `new_event_loop()` sync facade. This was fragile, leaked threads, and bypassed `base.py`'s checkpoint/resume infrastructure.
> - **Why it matters:** Understand was the only workflow that didn't support crash-checkpointing. If it crashed mid-parse, the entire workflow had to restart from scratch. The event loop hack could hang under certain conditions.
> - **Fix:** Converted all nodes to sync (`def`). Routed through `base.py`'s standard `graph.invoke()`. Removed the `ThreadPoolExecutor` + `new_event_loop()` facade entirely. Used `_parse_dependencies_sync_from_string()` directly instead of the async `parse_file_dependencies()` wrapper.

> - **What happened:** All nodes used hardcoded `tid` strings (`"understand_init"`, `"understand_discover"`, `"understand_parse"`) instead of `state.get("trace_id")`. Trace correlation was impossible.
> - **Fix:** Added `trace_id` to `UnderstandState` TypedDict. `_default_state()` now accepts `trace_id` parameter. All nodes use `state.get("trace_id", "understand")` as fallback.

> - **What happened:** [v1.4.1 P0-1] `node_init_project` could return `{"status": "failed", ...}` (source root missing, project too large, GraphStore init crash), but the graph had a DIRECT edge `init → discover`. `node_discover_files` ran anyway on a half-initialized project → found 0 files → `node_parse_and_store` returned "completed" → `node_report` said "✅ up to date". The user saw a green checkmark on a workflow that never actually indexed anything.
> - **Fix:** Added `route_after_init` (in `workflows/understand_impl/routes.py`) — conditional edge that routes to END when `status == "failed"`. Mirrors the autoresearch `route_after_setup` pattern. Belt-and-suspenders: discover + parse also bail early on `status == "failed"` (P1-1).

> - **What happened:** [v1.4.1 P1-7] `store = GraphStore(db_path)` was created BEFORE the `try` block. If the constructor raised (SQLite locked, disk full), `store` was undefined, and `finally: store.close()` raised `NameError`, masking the original exception.
> - **Fix:** `store = None` before `try`; `if store is not None: store.close()` in `finally`. Applied to both `discover_files` and `parse_and_store`.

> - **What happened:** [v1.4.1 P1-5] Failed embedding batches were logged via `tracer.warning` but NOT added to the `errors` list. Operators saw `vectors_created=5000` with no indication that 100 items were skipped.
> - **Fix:** `_batch_embed_and_store` now returns `tuple[int, list[str]]` (vectors_stored, errors). Failed batches (None embeddings, count mismatch, ChromaDB upsert exception) append an error string. The errors are merged into the node's main errors list.

> - **What happened:** [v1.4.1 P1-3] ChromaDB vectors were always stored at `cfg.agent_root / ".understand" / "chroma"` — the AGENT root, not the PROJECT root. Deleting a project's `.understand/` directory deleted the kg.db but left the project's vectors orphaned at the agent root.
> - **Fix:** `get_project_vector_collection(pm)` computes the path from `pm`: `{project}/.understand/chroma/` for projects, `memory_db/understand/chroma/` for agent root. Existing agent-root data should be manually deleted + re-indexed.

---

*Last updated: 2026-07-21 (v1.4.1). See [ARCHITECTURE.md](ARCHITECTURE.md) for file maps, [API.md](API.md) for node details, [CHANGELOG.md](CHANGELOG.md) for version history.*
