<- Back to [Memory Backend Overview](../MEMORY.md)

# 🗺️ Changelog

## 📝 Version History

| Version | Date | Changes |
|---------|------|---------|
| v1.2 | 2026-07-08 | **JSON schema enforcement:** `procedural/distill.py` now passes `json_schema` to `llm.complete()`. Schema: `{has_insight: bool, rule: str, tags: str}`. LM Studio enforces at generation time. Defensive JSON parsing stays as fallback. |
| v1.1 | 2026-07-08 | `store_chunked()` method + `execute_store_chunked()` — batch insert with hash-dedup-only (skips vector dedup for chunked stores). Recall returns `source_doc_id`/`chunk_index`/`chunk_count` metadata. `META_FIELDS` updated with 3 new fields. |
| v1.0 | — | Three-collection architecture, four-layer dedup, decay scoring, context budgeting, diversity enforcement, meta-learning, sleep-learn daemon, thread-safe writes, cancellation guards, telemetry |

---

## ⚠️ Breaking Changes (pre-v1.0)

| Old | New | Migration |
|-----|-----|-----------|
| `core/memory.py` facade | `core/memory_engine.py` | Update all imports: `from core.memory import memory` → `from core.memory_engine import memory` |
| `memory.remember(text, collection=...)` | `memory.store(text, memory_type=...)` | Use `store()` with `memory_type` param, or typed helpers `store_episodic()` / `store_semantic()` / `store_procedural()` |
| `memory.write_procedural_rule()` | `memory.store_procedural()` | Same API, different method name |
| `memory.forget(query, ...)` | `memory.delete(query, ...)` | Same behavior, renamed for clarity |
| `memory.memory_vacuum()` | `memory.prune()` | Prune handles stale entry removal |
| `memory.memory_report()` | `memory.stats()` | Stats returns collection counts and health |
| `memory.compact()` | Not implemented | Use `memory.stats()` to check collection health |
| `memory.deduplicate()` | Not implemented | Dedup happens automatically on every write |
| `memory.memory_search()` | `memory.recall()` | Same behavior, `recall()` is the unified search |
| `memory.semantic_search()` | `memory.recall()` | Same behavior |
| `core/context_budget.py` | `core/llm_backend/rate_limit.py` | Context budgeting moved to LLM backend |

---

## ✅ Completed

| Feature | Status | Notes |
|---------|--------|-------|
| `store_chunked()` + `execute_store_chunked()` | ✅ v1.1 | Batch insert for chunked stores. Hash-dedup-only (skips vector dedup — chunks from same doc would falsely trigger it). Linked via `source_doc_id` UUID + `chunk_index`/`chunk_count` metadata. |
| Recall returns chunk metadata | ✅ v1.1 | `source_doc_id`, `chunk_index`, `chunk_count` in recall results. Non-chunked memories return defaults (`""`, `None`, `0`). |
| `META_FIELDS` updated | ✅ v1.1 | Added `source_doc_id`, `chunk_index`, `chunk_count` (documentation-only — ChromaDB accepts arbitrary metadata keys). |
| Three-collection architecture | ✅ pre-v1 | Episodic, semantic, procedural |
| Four-layer dedup | ✅ pre-v1 | Hash guard + outer vector + inner vector + procedural reinforcement |
| Decay scoring | ✅ pre-v1 | Time-decay with procedural bypass |
| Context budgeting | ✅ pre-v1 | Cognitive priority-based message trimming (7-tier) |
| Diversity enforcement | ✅ pre-v1 | Autonomous procedural collection cleanup |
| Inline meta-learning | ✅ pre-v1 | `meta_learning.py` — fast, low-threshold |
| Background sleep-learning | ✅ pre-v1 | Daemon, feedback, distiller, filters, storage, injector |
| Thread-safe writes | ✅ pre-v1 | `_write_lock` with double-check locking |
| Cancellation guards | ✅ pre-v1 | `ensure_not_cancelled()` on all writes |
| Telemetry integration | ✅ pre-v1 | Opik observability for latency and dedup metrics |

---

## 🔄 In Progress / Next Up

| Feature | Notes | Priority |
|---------|-------|----------|
| Group-aware `delete` by `source_doc_id` | When deleting a chunked memory, offer to delete all chunks with the same `source_doc_id`. Prevents orphaned fragments. Currently `delete` is similarity-based and may match some chunks but not others. | P1 |
| Semantic chunking (`chunk_method="semantic"`) | Uses LM Studio `/v1/embeddings` for topic-aware splitting. Needs design decision on offline fallback. | P2 |
| Sweeper integration | Phase 1 passive observation only; needs tracer/memory integration | P1 |
| Janitor consolidation | `sleep_learn/janitor.py` has purge logic; `memory_backend/janitor.py` handles episodic archival | P1 |
| Consolidated learning pipeline | Merge inline + background into single system with `source` metadata | P2 |
| Context budget unification | Merge `core/memory_backend/budget.py` into `core/llm_backend/rate_limit.py` | P2 |
| Multi-modal memory | Image and audio embeddings | P3 |
| Memory graph | Relationship tracking between memories | P3 |
| Cross-session learning | Share learned rules across agent instances | P3 |

---

## 🚫 Deferred / Out of Scope

| # | Feature | Why Deferred | Priority |
|---|---------|------------|----------|
| 1 | Streaming memory writes | ChromaDB does not support streaming inserts | Skip |
| 2 | Distributed memory | Single-node ChromaDB is sufficient for current scale | Skip |
| 3 | Persistent event loop for writes | ThreadPoolExecutor per write is sufficient | Skip |
| 4 | Custom embedding models | `all-MiniLM-L6-v2` is fast and accurate enough | Skip |
| 5 | Real-time sync across agents | No multi-agent deployment currently | Skip |
| 6 | Configurable decay half-life | Hardcoded 30 days is appropriate for all use cases | Skip |
| 7 | TencentDB-style layered memory architecture (L0→L1→L2→L3) | Inspired by [TencentCloud/TencentDB-Agent-Memory](https://github.com/TencentCloud/TencentDB-Agent-Memory). Progressive disclosure: L0 raw conversation → L1 atomic facts → L2 scenario blocks → L3 user persona. Top layers in context, drill down for details. Our current sleep_learn distiller does similar L0→L1 distillation but without the full pyramid. Needs architectural design before implementation. | P2 |

---

*Last updated: 2026-07-08. See [ARCHITECTURE.md](ARCHITECTURE.md) for file maps, [API.md](API.md) for API reference, [INSTRUCTIONS.md](INSTRUCTIONS.md) for AI editing rules.*
