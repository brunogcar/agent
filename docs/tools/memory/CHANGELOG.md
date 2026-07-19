<- Back to [Memory Overview](../MEMORY.md)

# 🗺️ Changelog

## ✅ Completed

### 📝 Version History

| Version | Date | Summary |
|---------|------|---------|
| **v1.5** | 2026-07-17 | **L1 atomic fact extraction + tags_required (AND filtering).** (1) New `extract` action — router-tier LLM extracts atomic facts from text → `atomic` collection. TencentDB L1 layer. (2) `tags_required` parameter on `recall()` — AND-based tag filtering (ALL required tags must be present). (3) Tag validation regex updated to allow `:` (for `source:*`, `domain:*` prefixed tags). (4) Comprehensive docs audit: 15 files updated (factual errors fixed, stale references corrected, cross-links added, module trees updated). |
| **v1.4** | 2026-07-16 | **Memory tool maturity (pre-merge prep).** 4 new features: (1) `update` action — modify a memory by ID without delete+re-create. Tracks changes in a sidecar SQLite audit table (`memory_db/memory_audit.db`, `rule_history` table) — NOT in ChromaDB metadata (collective review: JSON string bloats queries). Append-only, queryable. (2) `export`/`import` actions — JSONL backup/restore. Needed for the Commit 4 migration (`procedural_meta` → `procedural`). (3) Group-aware `delete` by `source_doc_id` — deletes all chunks sharing a UUID. Prevents orphaned fragments. (4) `tags_required` deferred to Commit 5 (after tag schema is defined — collective review: AND-filter before schema is a bug). |
| v1.3.1 | 2026-07-12 | **`_mem()` singleton fix.** Was creating a NEW `MemoryStore()` instead of using the module-level singleton. Dedup broken between tool and workflow writes. Fixed + added `[DESIGN]` block. |
| v1.3 | 2026-07-08 | **Chonkie chunking on `store`.** `chunk`/`chunk_method`/`chunk_size` params. Semantic + episodic only; procedural rejected. Core `store_chunked()` backend. Recall returns `source_doc_id`/`chunk_index`/`chunk_count`. System prompt fixed (50KB limit). |
| v1.2 | — | `compress_result()` crash caught, `duration_ms` in all responses, `delete` validation, `recall_context` rejects unsupported params, `stats` validation, tag splitting, janitor guards, destructive actions documented. |
| v1.1 | — | `delete` with `confirm_ids` only, `collections` type validation, `prune` range validation, `janitor` exception guards, `compress_result` success-only, facade exception handling. |
| v1.0 | — | `@meta_tool` + `@register_action` auto-discovery, un-multiplex to `memory_ops/actions/*.py`, `recall_context` action, fail-fast validation, `state.py` singleton pattern. |

---

### ⚠️ Breaking Changes

#### v1.3 — 2026-07-08 (non-breaking additions)

| Change | Impact | Migration |
|--------|--------|-----------|
| New params on `store`: `chunk`, `chunk_method`, `chunk_size` | When `chunk=True`, text is split via chonkie into N linked chunks. | No migration — `chunk` defaults to `False`. |
| `chunk=True` rejected on `procedural` collection | Procedural reinforcement is nonsensical for chunks. | Returns clear error. |
| Core: `recall()` returns `source_doc_id`/`chunk_index`/`chunk_count` | Non-chunked memories return defaults (`""`, `None`, `0`). | No migration — additive metadata. |
| System prompt memory limit fix | "~450 chars" → "50KB (MAX_MEMORY_BYTES)" + `chunk=True` reference. | No migration. |

#### v1.0 — `@meta_tool` refactor

| Old | New | Migration |
|-----|-----|-----------|
| `core/memory.py` import | `core/memory_engine.py` | Internal change — no LLM-facing impact. |
| `tools/memory_tool.py` | `tools/memory.py` | Facade renamed; all imports updated. |
| Monolithic if/elif dispatch | `@meta_tool` + `@register_action` auto-discovery | Same API surface. |
| 7 actions | 8 actions | Added `recall_context`. |

### ✅ Recently Completed Features

| Feature | Version | Notes |
|---------|---------|-------|
| **`update` action** | ✅ v1.4 | Modify a memory by ID without delete+re-create. Sidecar SQLite audit log (`rule_history` table). |
| **`export`/`import` actions** | ✅ v1.4 | JSONL backup/restore. Path-guard validated. Used for the `procedural_meta` → `procedural` migration. |
| **Group-aware `delete` by `source_doc_id`** | ✅ v1.4 | Delete all chunks sharing a UUID in one call. Prevents orphaned fragments. |
| **AND-based tag filtering (`tags_required`)** | ✅ v1.5 (Commit 5) | Complements OR-based `tags_filter` for precise procedural recall. Deferred from v1.4 pending the tag schema (delivered in v1.2 unified rule schema). |

---

## 🔄 In Progress / Next Up

| # | Feature | Notes | Priority |
|---|---------|-------|----------|
| — | Semantic chunking (`chunk_method="semantic"`) | Uses LM Studio `/v1/embeddings` for topic-aware splitting. Needs design decision on offline fallback. | P2 |
| — | `memory(action="health")` | Lightweight ChromaDB connectivity check. | P2 |
| — | `store_batch` action | Store multiple independent memories in one call (not chunks — independent texts). Cap at 20 entries. | P2 |
| — | `recall_context` `tags_filter`/`min_score` support | Requires backend `execute_recall_context()` to accept these params. | P2 |
| — | `recent` action | Time-based retrieval (last N entries or N days). No similarity search needed. | P2 |
| — | `search` action (exact/keyword) | ChromaDB `$contains` search for exact phrases. Complement to semantic `recall`. | P2 |
| — | Query audit log | Append every recall/recall_context to `workspace/.artifacts/memory_queries.log`. | P2 |
| — | Decay score in recall results | Expose time/importance decay score alongside vector similarity. | P2 |
| 47 | Mermaid symbol graph for context offloading | TencentDB pattern. Instead of storing verbose memory entries, offload full text to files and replace with compact Mermaid symbols. 61% token reduction in their benchmarks. Complements chonkie for cross-field context management. | P3 |

---

## 🚫 Deferred / Out of Scope

| # | Feature | Why Deferred | Priority |
|---|---------|--------------|----------|
| 1 | Streaming memory writes | ChromaDB does not support streaming inserts. | Skip |
| 2 | Real-time memory sync | No multi-agent deployment currently. | Skip |
| 3 | Custom embedding models | `all-MiniLM-L6-v2` is fast and accurate enough. | Skip |
| 4 | Memory graph queries | Relationship tracking belongs in backend, not tool. | Skip |
| 5 | Typed convenience actions (`store_episodic`, etc.) | Bloats schema; LLM handles `memory_type` fine. | Skip |
| 6 | Tag auto-completion | Complex, low ROI; LLM generates tags well. | Skip |
| 7 | Memory versioning / diffs | Complex; audit trails belong in UI layer. | Skip |
| 8 | Collection migration | Only needed if schema changes; rare. | Skip |
| 9 | Namespace isolation | Only needed for multi-tenant deployments. | Skip |
| 10 | `PARALLEL_SAFE = True` for memory | ChromaDB SQLite backend is NOT thread-safe for concurrent writes on Windows. | Rejected |
| 11 | `error_code` in `fail()` responses | No consumer needs structured error codes for memory. | Rejected |
| 12 | `get` action (retrieve by ID) | Low value — the LLM never has IDs unless it just stored something. | Rejected |
| 13 | `clear` action (remove all memories) | Too dangerous — one misprompt wipes all memory. | Rejected |
| 14 | LRU cache for `recall` | Memory contents change between calls. Cached results would be stale. | Rejected |
| 15 | `inspect.signature` filtering in facade | Violates the established `_ops` pattern. | Rejected |
| 16 | Explicitly reject `collections` in `store` | Harmlessly absorbed by `**kwargs`. | Rejected |

---

*Last updated: 2026-07-18 (v1.6 — #47 symbol offloading).*
