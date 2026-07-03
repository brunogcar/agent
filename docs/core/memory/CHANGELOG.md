<- Back to [Memory Backend Overview](../MEMORY.md)

# 🗺️ Changelog

## 📝 Version History

| Version | Date | Changes |
|---------|------|---------|

*(Fill this section with relevant info from edits and refactors. Add version history as it is learned.)*

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

---

*Last updated: 2026-07-03. See [ARCHITECTURE.md](ARCHITECTURE.md) for file maps, [API.md](API.md) for API reference, [INSTRUCTIONS.md](INSTRUCTIONS.md) for AI editing rules.*
