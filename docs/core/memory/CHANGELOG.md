<- Back to [Memory Backend Overview](../MEMORY.md)

# 🗺️ Changelog

## ✅ Completed

### 📝 Version History

| Version | Date | Summary |
|---------|------|---------|
| **v1.5** | 2026-07-18 | **Post-merge cleanup (minimax review): 12 bugs fixed — 5 P0 + 4 P1 + 3 P2.** Closes the gap between the v1.2 unified rule schema contract and what the writers/injector actually wrote. **P0 (split-brain + confidence drift + reasoning end-to-end):** (1) `sleep_learn/injector.py` split-brain ACTUALLY fixed — `SLEEP_LEARN_UNIFIED` flag now gates the legacy `procedural_meta` query; when `true` (default) ONLY the unified `procedural` collection is queried. Also: literal `"daemon"` trace_id → `generate_trace_id()`; confidence read order canonical-first (`meta.get("confidence", meta.get("confidence_score", 0.0))`). (2) `sleep_learn/feedback.py update_rule_confidence()` now writes BOTH `meta["confidence"]` (canonical) AND `meta["confidence_score"]` (legacy mirror) — was only writing `confidence_score`, so the injector's canonical read saw stale data. Also reads canonical first; literal `"daemon"` trace_id → `tracer.new_trace()`. (3) `memory_backend/meta_learning.py` canonical tags: `tags="meta-learned,auto-distilled"` → `tags="source:meta_learner,category:auto_distilled"`; now calls `normalize_tags()` + `validate_tags()` before `memory.store()`. (4) `meta_learning.py` idle detection: `run_forever()` was `_time.sleep(1800)` unconditionally; now mirrors `sleep_learn/daemon.py` — `tracker.try_acquire_background_slot(min_idle_seconds=300)` + `Event.wait(timeout=1800)` (immune to `time.sleep` mocks); uses `tracer.new_trace()` per cycle. (5) `memory_backend/procedural/distill.py` `reasoning` field: `_DISTILL_JSON_SCHEMA` now has `reasoning: {type: string, maxLength: 500}` in properties + required; system prompt asks for it; `store_procedural()` signature extended with `reasoning: str = ""`, wired through `_store()` → `execute_store()` → `build_unified_metadata()`. Injector's `meta.get("reasoning", "")` now finds populated data. **P1 (dedup + tags + docstring + singleton):** (6) `memory_backend/atomic_extract.py` dedup: `min_score=0.0` (fetch all, post-filter) → `min_score=0.92` (let ChromaDB filter at the source — simpler + faster). (7) `atomic_extract.py` tag prefix: `type:{fact['type']}` → `category:{fact['type']}` (canonical — `type:` is not in `VALID_TAG_PREFIXES`). (8) `meta_learning.py` docstring: "UNIFICATION STATUS: Partial" → "Complete" (the injector split-brain is now actually fixed). (9) `tools/memory_ops/actions/update.py` singleton: `_get_audit_db()` was creating a new SQLite connection on every call (docstring said "Singleton per process" — it wasn't); now uses module-level `_audit_conn` + `_audit_lock` with double-checked locking; removed 3 `audit_conn.close()` calls that would break the shared connection. **P2 (documentation + field rename):** (10) `sleep_learn/janitor.py` comment clarified: Janitor Bypass is at the ACTION layer (`tools/memory_ops/actions/janitor.py` lazy-imports), not the function layer. (11) `sleep_learn/migrate.py` merge semantics documented: confidence=MAX (not average), recall_count NOT updated, last_accessed_at NOT updated, provenance_count recomputed from `source_trace_ids` union — all deliberate choices, not bugs. (12) `memory_backend/read_ops.py` field rename: `"trace_id"` → `"source_trace_id"` in recall results (was confusing — it's the memory's ORIGIN trace, not the current query's trace; matches the schema's `source_trace_ids` field naming). |
| **v1.4** | 2026-07-18 | **Observability v1.1 follow-up: `maintenance.py` uses `generate_trace_id()` not `new_trace()`.** The 4 `execute_*` functions (delete, prune, summarize, stats) only call `tracer.error()` — no `step`/`finish` events. Using `tracer.new_trace()` at the top of each function introduced side effects (file I/O write to `logs/agent/agent_YYYYMMDD.jsonl`, stderr print, `_TraceStore` insert) that interfered with ChromaDB query timing in `test_hash_cache_syncs_on_delete` — the just-stored memory wasn't found by the delete query, returning `status="no_match"` instead of `"deleted"` → `KeyError: 'count'`. Switched to `generate_trace_id()` (returns a unique 12-char hex ID with ZERO side effects). Error events still get a unique correlation ID; the JSONL log still records them via `tracer.error` → `_writer.write`. Also: janitor.py + meta_learning.py use `new_trace()` (they have `step`/`finish` calls, so the full trace is warranted). |
| **v1.3** | 2026-07-17 | **L1 atomic fact extraction (TencentDB-shaped).** New `core/memory_backend/atomic_extract.py` — router-tier LLM extracts atomic facts from episodic entries → new `atomic` collection. `extract_facts_from_episodic()` (LLM call, json_schema enforced) + `extract_and_store_facts()` (dedup + store). New memory tool action: `extract`. New collection constant `COLLECTION_ATOMIC`. `store_atomic()` method on MemoryStore. 10 tests. Completes L1→L2→L3 (episodic → atomic → procedural). L0 (working set) deferred. |
| **v1.2** | 2026-07-16 | **Unified rule schema (L3 contract) — the keystone of the Memory + Sleep_Learn merge.** New `core/memory_backend/rule_schema.py` defines the unified procedural rule shape that both writers (meta_learning + sleep_learn/distiller) will conform to. Key design (from 6-LLM collective review): (1) `importance` (1-10) + `confidence` (0.0-1.0) coexist — `normalize_rule_fields()` derives one from the other so both are always present. (2) `version` + `schema_version` for optimistic locking + future migrations. (3) `provenance_count` derived from `source_trace_ids` for fast filtering. (4) `updated_at` field (set by Commit 1's `update` action). (5) Tag schema enforced at write time — `validate_tags()` + `normalize_tags()` with canonical prefixes (`source:*`, `domain:*`, `category:*`, `status:*`, `evidence:*`). (6) `text_hash` kept for migration dedup. (7) `history` is NOT in ChromaDB metadata — lives in sidecar SQLite (Commit 1). (8) Procedural records are never chunked (stated explicitly). `build_unified_metadata()` is the single entry point both writers call. 28 tests. |
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

*Last updated: 2026-07-18 (v1.5 post-merge cleanup: 12 bugs fixed). See [ARCHITECTURE.md](ARCHITECTURE.md) for file maps, [API.md](API.md) for API reference, [INSTRUCTIONS.md](INSTRUCTIONS.md) for AI editing rules.*
