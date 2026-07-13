<- Back to [Memory Overview](../MEMORY.md)

# 🗺️ Changelog

## 📝 Version History

| Version | Date | Changes |
|---------|------|---------|
| v1.3.1 | 2026-07-12 | **[Bugfix] `_mem()` singleton fix.** `helpers._mem()` was creating a NEW `MemoryStore()` instance instead of using the module-level singleton from `core.memory_engine.memory`. Two separate instances had separate `_hash_cache` sets (dedup broken between tool and workflow writes — a tool `store()` and a workflow `store()` could write the same memory twice) and separate `_write_lock` instances (the TOCTOU double-checked locking fix in `write_ops.py` was bypassed). Fixed: `_mem()` now imports `memory as _singleton` from `core.memory_engine` and assigns that to `state._store`. Also added `[DESIGN]` block to `helpers.py` documenting the singleton constraint. |
| v1.3 | 2026-07-08 | Chonkie chunking on `store` action (`chunk`, `chunk_method`, `chunk_size` params). Semantic + episodic only; procedural rejected. Core `store_chunked()` backend (hash-dedup-only, batch insert). Recall returns `source_doc_id`/`chunk_index`/`chunk_count` metadata. System prompt fixed (50KB limit, not 450 chars). |
| v1.2 | — | `compress_result()` crash caught, `duration_ms` in all responses, `delete` confirm_ids/threshold validation, `recall_context` rejects unsupported params, `stats` collections validation, tag splitting comma-only, janitor errors forced to strings, destructive actions documented |
| v1.1 | — | `delete` with `confirm_ids` only, `collections` type validation, `prune` range validation, `janitor` exception guards, `compress_result` success-only, facade exception handling |
| v1.0 | — | `@meta_tool` + `@register_action` auto-discovery, un-multiplex to `memory_ops/actions/*.py`, `recall_context` action, fail-fast `memory_type` validation, reject empty `collections=[]`, `state.py` singleton pattern |

---

## ⚠️ Changelog

### v1.0

| Old | New | Migration |
|-----|-----|-----------|
| `core/memory.py` import | `core/memory_engine.py` | Internal change — no LLM-facing impact |
| `tools/memory_tool.py` | `tools/memory.py` | Facade renamed; all imports updated |
| `tools/memory_tool.py` monolith | `tools/memory_ops/actions/*.py` | Logic split into 8 atomic action files |
| `tests/tools/memory_tool/` | `tests/tools/memory/` | Test folder renamed; monolithic tests split |
| Monolithic if/elif dispatch | `@meta_tool` + `@register_action` auto-discovery | Same API surface; internal architecture changed |
| 7 actions | 8 actions | Added `recall_context` (formatted string for prompt injection) |

### v1.1

| Change | Impact |
|--------|--------|
| `delete` now accepts `confirm_ids` without `query` | ID-only deletion works; previously required dummy query |
| `delete` validates `collections` type | Non-list `collections` (e.g., string) now rejected with clear error |
| `prune` validates `max_age_days >= 0` and `min_importance` 1–10 | Previously passed unchecked to backend |
| `summarize` validates `collections` | Empty `collections=[]` now rejected |
| `janitor` handles exceptions and non-dict returns | Previously crashed on unexpected return types |
| `compress_result()` only on success | Error responses no longer shallow-copied by compressor |
| Facade catches handler exceptions | Previously uncaught exceptions crashed the tool |

### v1.3 (non-breaking additions)

| Change | Impact |
|--------|--------|
| New params on `store`: `chunk` (bool, default False), `chunk_method` ("token"\|"sentence", default "token"), `chunk_size` (int, default 512) | When `chunk=True`, text is split via chonkie into N linked chunks, each stored as a separate memory with shared `source_doc_id` metadata. Enables precise recall (find the specific paragraph, not the whole document). |
| `chunk=True` rejected on `procedural` collection | Procedural reinforcement (increment `reinforcement_count` on semantic match) is nonsensical for chunks — which chunk gets reinforced? Returns clear error. |
| Core: new `store_chunked()` method on `MemoryStore` | Batch insert with hash-dedup-only (skips vector dedup — chunks from the same document would falsely trigger it). See `docs/core/memory/CHANGELOG.md` v1.1. |
| Core: `recall()` returns `source_doc_id`, `chunk_index`, `chunk_count` | LLM can identify recall results as fragments of a larger document. Non-chunked memories return defaults (`""`, `None`, `0`). |
| System prompt fixed | `docs/system_prompts/system_prompt.md` rule #6 was "~450 chars per entry" — incorrect. Actual limit is 50KB (`MAX_MEMORY_BYTES`). Updated to reference `chunk=True` for large documents. |
| Reuses `_chunk_text()` from `tools/file_ops/actions/read_file.py` | Same chonkie integration as file tool v1.2. Soft dependency (lazy import). No code duplication. |
| No existing params removed or renamed | v1.2 callers unaffected — `chunk` defaults to `False` |

---

## ✅ Completed

| Feature | Status | Notes |
|---------|--------|-------|
| Chonkie chunking on `store` action | ✅ v1.3 | `chunk=True` splits text via chonkie (token/sentence). Semantic + episodic only; procedural rejected. Reuses `_chunk_text()` from file tool. |
| Core `store_chunked()` backend | ✅ v1.3 | Batch insert, hash-dedup-only (skips vector dedup). See `docs/core/memory/CHANGELOG.md` v1.1. |
| Recall returns chunk metadata | ✅ v1.3 | `source_doc_id`, `chunk_index`, `chunk_count` in recall results. Non-chunked memories return defaults. |
| System prompt memory limit fix | ✅ v1.3 | "~450 chars" → "50KB (MAX_MEMORY_BYTES)" + chunk=True reference |
| Monolithic `memory(action, ...)` dispatch | ✅ pre-v1 | Single `@tool` function with if/elif branching |
| Lazy ChromaDB loading | ✅ pre-v1 | `_mem()` closure; janitor bypasses store entirely |
| 7 actions (store/recall/delete/prune/summarize/stats/janitor) | ✅ pre-v1 | All wired to `core.memory_engine.MemoryStore` |
| Tag validation (MED-05) | ✅ pre-v1 | XSS/injection prevention, length limits, character whitelist |
| Result compression | ✅ pre-v1 | `compress_result()` on success outputs |
| Trace ID threading | ✅ pre-v1 | Propagated through all action results |
| Janitor bypass optimization | ✅ pre-v1 | `archive_old_episodes()` + `purge_stale_rules()` without store load |
| `@meta_tool` + `@register_action` auto-discovery | ✅ v1.0 | `Literal` enum, dynamic docstring, no central wiring |
| Un-multiplex to `memory_ops/actions/*.py` | ✅ v1.0 | 8 atomic action files |
| Rename `tools/memory_tool.py` → `tools/memory.py` | ✅ v1.0 | Facade renamed; all imports updated |
| Rename test folder `memory_tool/` → `memory/` | ✅ v1.0 | Monolithic tests split into per-action files |
| Add `conftest.py` with shared fixtures | ✅ v1.0 | `reset_memory_state`, `mock_store`, `mock_cfg` |
| Split tests into per-action files | ✅ v1.0 | `test_store.py`, `test_recall.py`, etc. |
| Add `test_tag_validation.py` | ✅ v1.0 | Dedicated MED-05 coverage |
| Add `test_facade.py` | ✅ v1.0 | `@meta_tool` metadata, action Literal, unknown action guard |
| Add `test_registry.py` | ✅ v1.0 | `DISPATCH` dict, `@register_action`, duplicate guard |
| Add `recall_context` action | ✅ v1.0 | Formatted string for direct prompt injection |
| Fail-fast `memory_type` validation | ✅ v1.0 | Reject invalid types instead of silent coercion to "semantic" |
| Reject empty `collections=[]` | ✅ v1.0 | Prevent silent all-collections fallback |
| `state.py` singleton pattern | ✅ v1.0 | Isolated `_store` with `reset_state()` for tests |
| Facade exception handling | ✅ v1.1 | Handler exceptions caught and returned as structured `fail()` |
| `compress_result` success-only | ✅ v1.1 | Skip compression on error responses |
| `collections` type validation | ✅ v1.1 | Reject non-list types (strings, etc.) |
| `delete` with `confirm_ids` only | ✅ v1.1 | No longer requires dummy query |
| `delete` `threshold=0.0` preservation | ✅ v1.1 | Passed as `0.0`, not converted to `None` |
| `prune` range validation | ✅ v1.1 | `max_age_days >= 0`, `min_importance` 1–10 |
| `janitor` exception + non-dict guards | ✅ v1.1 | Continues after partial failures |
| `summarize` `collections` validation | ✅ v1.1 | Empty list rejected |
| `summarize` `trace_id` pass-through | ✅ v1.1 | Passed to backend `store.summarize()` |
| `test_helpers.py` | ✅ v1.1 | Dedicated tests for validation functions and singleton |
| `compress_result` crash caught | ✅ v1.2 | Returns structured `fail()` instead of leaking exception |
| `duration_ms` in all responses | ✅ v1.2 | Performance monitoring for every action |
| `delete` `confirm_ids` type guard | ✅ v1.2 | String `confirm_ids` rejected |
| `delete` `threshold` range check | ✅ v1.2 | Must be 0.0–1.0 |
| `recall_context` rejects unsupported params | ✅ v1.2 | `tags_filter`/`min_score` fail fast |
| `stats` `collections` validation | ✅ v1.2 | Consistent with other actions |
| Tag splitting comma-only | ✅ v1.2 | Multi-word tags preserved |
| Janitor errors forced to strings | ✅ v1.2 | Prevents JSON serialization failures |
| Destructive actions documented | ✅ v1.2 | `delete`/`prune` flagged for human confirmation |

---

## 🔄 In Progress / Next Up

| Feature | Notes | Priority |
|---------|-------|----------|
| Group-aware `delete` by `source_doc_id` | When deleting a chunked memory, offer to delete all chunks with the same `source_doc_id`. Prevents orphaned fragments. | P1 |
| Semantic chunking (`chunk_method="semantic"`) | Uses LM Studio `/v1/embeddings` for topic-aware splitting. Needs design decision on offline fallback (LM Studio down → sentence chunking?). | P2 |
| `export`/`import` actions | JSONL backup/restore for collections. Needs file path validation (path guard). | P1 |
| AND-based tag filtering (`tags_required`) | Current `tags_filter` is OR-based. AND filtering for precise procedural recall. | P1 |
| `memory(action="health")` | Lightweight ChromaDB connectivity check. | P2 |
| `store_batch` action | Store multiple independent memories in one call (not chunks — independent texts). Cap at 20 entries. | P2 |
| `recall_context` `tags_filter`/`min_score` support | Requires backend `execute_recall_context()` to accept these params. | P2 |
| `update` action | Modify existing memory by ID without losing history or changing ID. | P1 |
| `recent` action | Time-based retrieval (last N entries or N days). No similarity search needed. | P2 |
| `search` action (exact/keyword) | ChromaDB `$contains` search for exact phrases. Complement to semantic `recall`. | P2 |
| Query audit log | Append every recall/recall_context to `workspace/.artifacts/memory_queries.log`. | P2 |
| Decay score in recall results | Expose time/importance decay score alongside vector similarity. | P2 |

---

## 🚫 Rejected / Out of Scope

| # | Feature | Why Rejected | Decision |
|---|---------|--------------|----------|
| 1 | Streaming memory writes | ChromaDB does not support streaming inserts | Skip |
| 2 | Real-time memory sync | No multi-agent deployment currently | Skip |
| 3 | Custom embedding models | `all-MiniLM-L6-v2` is fast and accurate enough | Skip |
| 4 | Memory graph queries | Relationship tracking belongs in backend, not tool | Skip |
| 5 | Typed convenience actions (`store_episodic`, etc.) | Bloats schema; LLM handles `memory_type` fine | Skip |
| 6 | Tag auto-completion | Complex, low ROI; LLM generates tags well from context | Skip |
| 7 | Memory versioning / diffs | Complex; audit trails belong in UI layer | Skip |
| 8 | Collection migration | Only needed if schema changes; rare | Skip |
| 9 | Namespace isolation | Only needed for multi-tenant deployments | Skip |
| 10 | `PARALLEL_SAFE = True` for memory | ChromaDB SQLite backend is NOT thread-safe for concurrent writes on Windows. The `_write_lock` in `MemoryStore` only guards the Python hash cache, not the underlying SQLite. Keep `memory` out of `PARALLEL_SAFE`. | Rejected |
| 11 | `error_code` in `fail()` responses | No consumer needs structured error codes for memory. The `status: "error"` + `error` message is sufficient. Tavily uses error codes because it hits external APIs with specific failure modes (auth, quota, network). Memory errors are all input validation or backend unavailability. | Rejected |
| 12 | `get` action (retrieve by ID) | Low value — the LLM never has IDs unless it just stored something. `recall` by query is the primary access pattern. | Rejected |
| 13 | `clear` action (remove all memories) | Too dangerous — one misprompt wipes all memory. `prune` with `dry_run=False` is already risky enough. | Rejected |
| 14 | LRU cache for `recall` | Memory contents change between calls. Cached recall results would be stale. The ChromaDB query is already fast (~5ms). Caching adds complexity and stale data risk for negligible gain. | Rejected |
| 15 | `inspect.signature` filtering in facade | Violates the established `_ops` pattern (git, file, browser all use `**kwargs` in handlers). Adds fragility — if a handler signature changes, the facade filter must be updated. The `**kwargs` absorption is a documented trade-off. | Rejected |
| 16 | Explicitly reject `collections` in `store` | The `collections` param is harmlessly absorbed by `**kwargs`. Rejecting it adds friction for the LLM which sees the param in the facade signature. The `memory_type` parameter determines the collection — this is by design. | Rejected |
| 17 | Mermaid symbol graph for context offloading (TencentDB pattern) | Inspired by [TencentCloud/TencentDB-Agent-Memory](https://github.com/TencentCloud/TencentDB-Agent-Memory). Instead of storing verbose memory entries, offload full text to files and replace with compact Mermaid symbols in context. Agent drills down via `node_id` when needed. 61% token reduction in their benchmarks. Would require restructuring how memory entries are stored + retrieved. | P3 |

---

*Last updated: 2026-07-08. See [ARCHITECTURE.md](ARCHITECTURE.md) for file maps, [API.md](API.md) for action details, [INSTRUCTIONS.md](INSTRUCTIONS.md) for AI editing rules.*
