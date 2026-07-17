<- Back to [Sleep & Learn Overview](../SLEEP_LEARN.md)

# 🗺️ Changelog

## 📝 Version History

| Version | Date | Notes |
|---------|------|-------|
| **v1.0** | 2026-07-16 | **Sleep_learn maturation (Commit 3 of the Memory + Sleep_Learn merge).** (1) **Idle detection** — daemon now gates on `tracker.try_acquire_background_slot()` before running. Prevents unnecessary resource usage in test/short-lived sessions (collective review: "runs unconditionally at startup" was the #1 complaint). (2) **Sweeper integration** — replaced the Phase 1 placeholder with real `tracer.recent()` + `memory.recall()` reads. Finds errors, retries, corrections, and failures from execution traces + episodic memories. Filters by signal strength (high/medium/low). Caps at 50 observations. (3) **Rule explanation** — injector now includes `reasoning` field (why the rule was learned) alongside the rule text in the injected prompt. (4) **Retrieval ranking formula** — defined: `rank_score = similarity * confidence`. Rules are sorted by combined score before injection (minimax's point: the formula must be defined, not undefined). (5) **Distiller output alignment** — `save_rule()` now uses `build_unified_metadata()` from the rule schema (Commit 2). Output conforms to the L3 contract so the migration (Commit 4) needs no schema conversion. Backward-compat fields (`confidence_score`, `phase`) kept until migration. |
| **v1.0+ (Commit 4)** | 2026-07-16 | **Migration: `procedural_meta` → `procedural`.** (1) `SLEEP_LEARN_UNIFIED` flag (default `true`) — when true, all sleep_learn writers (storage, feedback, janitor) use the main memory's `procedural` collection instead of the isolated `procedural_meta`. (2) Migration script (`core/sleep_learn/migrate.py`) — reads all rules from `procedural_meta`, deduplicates by `text_hash`, merges on collision (keeps higher confidence, unions `source_trace_ids`), writes to `procedural` with the unified schema, then drops `procedural_meta`. Idempotent. (3) Injector split-brain fallback updated — reads from unified `procedural` collection using the `confidence` field (was `importance` clamped). The `confidence_score` filter updated to `confidence` (unified schema). (4) No files deleted — `core/sleep_learn/` stays (daemon, distiller, feedback, etc. all still needed). The `procedural_meta` ChromaDB collection is dropped (data, not a file). The split-brain fallback code block in `injector.py` is replaced with a unified read. `purge_stale_rules()` stays in `sleep_learn/janitor.py` (preserves the Janitor Bypass pattern) but now operates on the unified collection. |
| Pre-v1 | 2026-07-08 | **JSON schema enforcement:** `distiller.py` now passes `json_schema` alongside existing `json_mode=True`. Schema: `{rule: str, confidence: number}`. LM Studio enforces at generation time. |
| Pre-v1 | 2026-07-04 | Initial implementation. Background meta-cognition daemon with feedback loop, distillation, quality filters, isolated storage, prompt injection, janitor. |

---

## ⚠️ Breaking Changes

| Old | New | Migration |
|-----|-----|-----------|
| `core/memory.py` import in injector | `core/memory_engine.py` | `from core.memory_engine import memory` |
| `process_pending_feedback()` | `process_feedback()` | Function renamed |
| `distill_rules(traces: list)` | `distill_observation(observation: dict)` | Single-observation, not batch |
| `filter_new_rules(rules: list)` | `is_quality_rule(rule_text: str)` | Single-rule validation |
| `store_rule(rule: dict)` | `save_rule(rule_text, source_memory_id, confidence)` | Direct storage API |
| `memory_sleep.remember()` | `save_rule()` via isolated ChromaDB client | No `memory_sleep` facade |
| 15s distiller timeout | 60s timeout | Intentional for local model stability |
| `SLEEP_MIN_IDLE_SECONDS` | `SLEEP_LEARN_IDLE_THRESHOLD_SEC` | Default 3600s, not 7200s |
| `SLEEP_CONFIDENCE_THRESHOLD` (0.6) | `SLEEP_LEARN_MIN_CONFIDENCE` (0.8) | Higher threshold for background learning |

---

## ✅ Completed

| Feature | Status | Notes |
|---------|--------|-------|
| Feedback processing | ✅ Pre-v1 | Parse logs, update confidence scores |
| Distillation | ✅ Pre-v1 | LLM-based rule extraction with 60s timeout |
| Quality filters | ✅ Pre-v1 | Generic, duplicate, and contradiction detection |
| Isolated storage | ✅ Pre-v1 | Separate ChromaDB instance for learned rules |
| Prompt injection | ✅ Pre-v1 | Merge rules into Planner system prompt |
| Feedback loop | ✅ Pre-v1 | Confidence boost/penalty based on outcomes |
| Janitor | ✅ Pre-v1 | `purge_stale_rules()` — confidence + age-based purging |
| Lazy loading | ✅ Pre-v1 | All ChromaDB imports inside functions |
| Zero coupling | ✅ Pre-v1 | Feedback reads JSONL directly, never imports tracer |
| Idle detection | ✅ v1.0 | `tracker.try_acquire_background_slot(min_idle_seconds=300)` gate before daemon runs |
| Sweeper integration | ✅ v1.0 | Replaced Phase 1 placeholder with `tracer.recent()` + `memory.recall()` reads; 50-observation cap |
| Rule explanation | ✅ v1.0 | Injector includes `reasoning` field alongside rule text in the injected prompt |

---

## 🔄 In Progress / Next Up

| Feature | Notes | Priority |
|---------|-------|----------|
| Consolidated learning | Merge inline + background into single pipeline with `source` metadata | P2 |
| Cross-session learning | Share learned rules across agent instances | P3 |
| Rule visualization | Dashboard showing active rules and their scores | P3 |

---

## 🚫 Deferred / Out of Scope

| # | Feature | Why Deferred | Priority |
|---|---------|------------|----------|
| 1 | Real-time distillation | Would compete with user-facing LLM calls for VRAM | Skip |
| 2 | Multi-agent rule sharing | No multi-agent deployment currently | Skip |
| 3 | Persistent background thread | `daemon=True` thread dies with main process; sufficient for current use | Skip |
| 4 | Custom distillation models | `llm.complete(role="executor")` is the canonical path | Skip |
| 5 | Rule editing via tool action | Rules are auto-generated; manual editing invites inconsistency | Skip |
| 6 | Configurable idle threshold | `SLEEP_LEARN_IDLE_THRESHOLD_SEC` exists but is not enforced yet | Skip |
| 7 | Layered memory pyramid (L0→L1→L2→L3) inspired by TencentDB Agent Memory | Our sleep_learn distiller does L0 (conversation) → L1 (atomic facts) distillation. TencentDB adds L2 (scenario blocks) + L3 (user persona) layers with progressive disclosure. Would make cross-session learning more structured. See [TencentCloud/TencentDB-Agent-Memory](https://github.com/TencentCloud/TencentDB-Agent-Memory). | P2 |

---

*Last updated: 2026-07-17. See [ARCHITECTURE.md](ARCHITECTURE.md) for file maps, [API.md](API.md) for method details, [INSTRUCTIONS.md](INSTRUCTIONS.md) for AI editing rules.*
