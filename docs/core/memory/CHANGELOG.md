<- Back to [Memory Backend Overview](../MEMORY.md)

# 🗺️ Changelog

## ✅ Completed

### 📝 Version History

| Version | Date | Summary |
|---------|------|---------|
| v1.2 | 2026-07-08 | **JSON schema enforcement.** `procedural/distill.py` passes `json_schema` to `llm.complete()`. Schema: `{has_insight: bool, rule: str, tags: str}`. |
| v1.1 | 2026-07-08 | **`store_chunked()` + chunk metadata.** Batch insert with hash-dedup-only. Recall returns `source_doc_id`/`chunk_index`/`chunk_count`. `META_FIELDS` updated. |
| v1.0 | — | **Initial release.** Three-collection architecture, four-layer dedup, decay scoring, context budgeting, diversity enforcement, meta-learning, sleep-learn daemon, thread-safe writes, cancellation guards, telemetry. |

---

### ⚠️ Breaking Changes

#### Pre-v1.0

| Old | New | Migration |
|-----|-----|-----------|
| `core/memory.py` facade | `core/memory_engine.py` | Update imports: `from core.memory import memory` → `from core.memory_engine import memory`. |
| `memory.remember(text, collection=...)` | `memory.store(text, memory_type=...)` | Use `store()` with `memory_type` param, or typed helpers. |
| `memory.write_procedural_rule()` | `memory.store_procedural()` | Same API, different method name. |
| `memory.forget(query, ...)` | `memory.delete(query, ...)` | Renamed for clarity. |
| `memory.memory_vacuum()` | `memory.prune()` | Renamed. |
| `memory.memory_report()` | `memory.stats()` | Renamed. |
| `memory.memory_search()` / `memory.semantic_search()` | `memory.recall()` | Unified search. |
| `core/context_budget.py` | `core/llm_backend/rate_limit.py` | Context budgeting moved to LLM backend. |

---

## 🔄 In Progress / Next Up

| # | Feature | Notes | Priority |
|---|---------|-------|----------|
| 46 | **Group-aware `delete` by `source_doc_id`** | When deleting a chunked memory, offer to delete all chunks with the same `source_doc_id`. Prevents orphaned fragments. Currently `delete` is similarity-based and may match some chunks but not others. Tool exposes this — see `docs/tools/memory/CHANGELOG.md` (same item). | P1 |
| — | Sweeper integration | Phase 1 passive observation only; needs tracer/memory integration. | P1 |
| — | Janitor consolidation | `sleep_learn/janitor.py` has purge logic; `memory_backend/janitor.py` handles episodic archival. | P1 |
| 45 | **TencentDB layered memory (L0→L1→L2→L3)** | Progressive disclosure pyramid: L0 raw conversation → L1 atomic facts → L2 scenario blocks → L3 user persona. Top layers in context, drill down for details. Our current sleep_learn distiller does similar L0→L1 distillation but without the full pyramid. Needs architectural design. | P2 |
| — | Semantic chunking (`chunk_method="semantic"`) | Uses LM Studio `/v1/embeddings` for topic-aware splitting. Needs design decision on offline fallback. | P2 |
| — | Consolidated learning pipeline | Merge inline + background into single system with `source` metadata. | P2 |
| — | Context budget unification | Merge `core/memory_backend/budget.py` into `core/llm_backend/rate_limit.py`. | P2 |
| — | Multi-modal memory | Image and audio embeddings. | P3 |
| — | Memory graph | Relationship tracking between memories. | P3 |
| — | Cross-session learning | Share learned rules across agent instances. | P3 |

---

## 🚫 Deferred / Out of Scope

| # | Feature | Why Deferred | Priority |
|---|---------|--------------|----------|
| 1 | Streaming memory writes | ChromaDB does not support streaming inserts. | Skip |
| 2 | Distributed memory | Single-node ChromaDB is sufficient for current scale. | Skip |
| 3 | Persistent event loop for writes | ThreadPoolExecutor per write is sufficient. | Skip |
| 4 | Custom embedding models | `all-MiniLM-L6-v2` is fast and accurate enough. | Skip |
| 5 | Real-time sync across agents | No multi-agent deployment currently. | Skip |
| 6 | Configurable decay half-life | Hardcoded 30 days is appropriate for all use cases. | Skip |

---

*Last updated: 2026-07-14. See [ARCHITECTURE.md](ARCHITECTURE.md) for file maps, [API.md](API.md) for API reference, [INSTRUCTIONS.md](INSTRUCTIONS.md) for AI editing rules.*
