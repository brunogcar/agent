# 💤 Sleep & Learn

The Sleep & Learn daemon (`core/sleep_learn/`) is a **background meta-cognition subsystem** that allows the agent to observe its own execution traces, distill procedural rules from successes and failures, and dynamically inject those rules into the Planner's context to improve future decision-making.

**Key characteristics:**
- **Background execution** — Runs at startup and catches midnight if the agent stays running; never during active use
- **Physical isolation** — Learned rules stored in separate ChromaDB instance (`procedural_meta`). **v1.0 (Commit 4): unified into the main `procedural` collection (`SLEEP_LEARN_UNIFIED=true`); `procedural_meta` is deprecated/migrated.**
- **Quality gates** — Multiple filters reject generic, contradictory, or dangerous rules
- **Feedback loop** — Rules are scored dynamically: boosted on success, penalized on failure
- **Ouroboros prevention** — Daemon never reads its own output collection during distillation
- **Zero coupling** — Feedback reads JSONL logs directly, never imports tracer or workflows

---

## 🚀 Quick Start

```python
from core.sleep_learn.injector import inject_rules_into_prompt

# Inject learned rules into a Planner prompt
enhanced_prompt = inject_rules_into_prompt(
    goal="fix memory import error",
    system_prompt="You are a coding assistant...",
    trace_id="abc123"
)

# Run feedback processing manually
from core.sleep_learn.feedback import process_feedback
stats = process_feedback()
# → {"processed": 5, "boosted": 3, "penalized": 1, "purged": 0, "errors": 0}

# Distill a single observation into a rule
from core.sleep_learn.distiller import distill_observation
result = distill_observation({
    "event_type": "error",
    "message": "ChromaDB query failed because collection was not initialized",
    "memory_id": "obs-001"
})
# → {"status": "success", "rule_id": "abc123", "rule_preview": "When ChromaDB returns empty..."}
```

---

## ⚙️ Configuration

### Environment Variables

| Env Variable | Default | Description |
|--------------|---------|-------------|
| `SLEEP_LEARN_ENABLED` | `true` | Toggle the entire daemon |
| `SLEEP_LEARN_UNIFIED` | `true` | **v1.0 (Commit 4):** When true, writers (storage, feedback, janitor) target the main `procedural` collection instead of the isolated `procedural_meta`. The unified rule schema (`core/memory_backend/rule_schema.py`) is used. |
| `SLEEP_LEARN_IDLE_THRESHOLD_SEC` | `3600` (1h) | Minimum idle time before background learning — **v1.0: now enforced** via `tracker.try_acquire_background_slot(min_idle_seconds=300)` |
| `SLEEP_LEARN_MIN_RULE_WORDS` | `10` | Minimum words per extracted rule |
| `SLEEP_LEARN_MAX_DAILY_DISTILLATIONS` | `20` | Maximum distillation runs per day |
| `SLEEP_LEARN_INJECT_ENABLED` | `true` | Kill switch for rule injection |
| `SLEEP_LEARN_MIN_CONFIDENCE` | `0.8` | Minimum confidence for rule extraction |
| `SLEEP_LEARN_MAX_INJECTED_RULES` | `3` | Maximum rules injected into Planner prompt |

### Tuning Guide

| Scenario | What to Adjust | Recommendation |
|----------|---------------|----------------|
| Rules not appearing | `SLEEP_LEARN_MIN_CONFIDENCE` | Lower to `0.7` for faster iteration |
| Too many low-quality rules | `SLEEP_LEARN_MIN_CONFIDENCE` | Raise to `0.85` or `0.9` |
| Rules too generic | `SLEEP_LEARN_MIN_RULE_WORDS` | Raise to `15` or `20` |
| Daemon not triggering | Check `start_background_daemon()` call site | Ensure called in `server.py` startup |
| Distiller timing out | Check LLM server health | The 60s timeout is intentional for local model stability |

---

## 🔄 When to Use

| Scenario | Method | Why |
|----------|--------|-----|
| Inject rules into Planner | `inject_rules_into_prompt()` | Improves future decision-making |
| Process feedback manually | `process_feedback()` | Update confidence scores |
| Distill an observation | `distill_observation()` | Extract a rule from a single event |
| Check rule quality | `is_quality_rule()` | Validate before storage |
| Purge stale rules | `purge_stale_rules()` | Maintenance cleanup |
| Background learning | `start_background_daemon()` | Automatic at startup + midnight |

---

## 📂 Documentation

> **See also:** [MEMORY.md](MEMORY.md) — the memory backend that sleep_learn now writes to (unified `procedural` collection, v1.0 Commit 4).

| File | Description |
|------|-------------|
| [ARCHITECTURE.md](sleep_learn/ARCHITECTURE.md) | Module tree, data flow, relationship to meta-learning, execution flow, hard guardrails, known concerns, testing |
| [API.md](sleep_learn/API.md) | All components (daemon, logger, feedback, distiller, filters, storage, injector, sweeper, janitor), API reference, breaking changes |
| [CHANGELOG.md](sleep_learn/CHANGELOG.md) | Version history, completed milestones, roadmap |
| [INSTRUCTIONS.md](sleep_learn/INSTRUCTIONS.md) | AI editing rules — NEVER DO, ALWAYS DO, anti-patterns |

---

---

## 🔧 v1.1 Observability Fix (2026-07-18)

Two files fixed:
- **`core/sleep_learn/feedback.py`** — `process_feedback()` was using `tracer.step("daemon", ...)` with a literal string `trace_id`. Now uses `_daemon_tid = tracer.new_trace("sleep_learn", goal="feedback cycle")`.
- **`core/sleep_learn/migrate.py`** — `migrate_rules()` had TWO bugs:
  1. Used literal string `"migration"` as `trace_id`.
  2. **NameError**: `_mig_tid` was only assigned inside the "drop collection" try block, so `dry_run=True` or `errors>0` caused `NameError` at the final `tracer.step(_mig_tid, ...)`.
  Now `_mig_tid` is created at the TOP of the function.

See [observability/CHANGELOG.md](observability/CHANGELOG.md) for details.

## 🔧 v1.2 Post-Merge Cleanup (2026-07-18)

12 bugs fixed across the memory + sleep_learn subsystem (minimax post-merge review). Closes the gap between the v1.2 unified rule schema contract (memory `v1.2`) and what the writers/injector actually wrote at runtime.

### P0 (5 bugs — split-brain, confidence drift, reasoning end-to-end)

| # | File | Fix |
|---|------|-----|
| 1 | `sleep_learn/injector.py` | **Split-brain ACTUALLY fixed.** `SLEEP_LEARN_UNIFIED` flag now gates the legacy `procedural_meta` query — when `true` (default) ONLY the unified `procedural` collection is queried (was querying both unconditionally → rules appeared twice or the legacy read masked the unified read). Also: literal `"daemon"` trace_id → `generate_trace_id()` on the error path; confidence read order canonical-first (`meta.get("confidence", meta.get("confidence_score", 0.0))`). |
| 2 | `sleep_learn/feedback.py` | `update_rule_confidence()` now writes BOTH `meta["confidence"]` (canonical) AND `meta["confidence_score"]` (legacy mirror) — was only writing `confidence_score`, so the injector's canonical read saw STALE data (boosts/penalties never reached the Planner). Also reads canonical first; literal `"daemon"` trace_id → `tracer.new_trace("sleep_learn", goal="feedback cycle")`. |
| 3 | `memory_backend/meta_learning.py` | Canonical tags: `tags="meta-learned,auto-distilled"` → `tags="source:meta_learner,category:auto_distilled"` (bare tags fail `validate_tags()`). Now calls `normalize_tags()` + `validate_tags()` before `memory.store()`. |
| 4 | `memory_backend/meta_learning.py` | Idle detection added to `run_forever()`: was `_time.sleep(1800)` unconditionally; now mirrors `sleep_learn/daemon.py` — `tracker.try_acquire_background_slot(min_idle_seconds=300)` + `Event.wait(timeout=1800)` (immune to `time.sleep` mocks). Uses `tracer.new_trace()` per cycle. |
| 5 | `memory_backend/procedural/distill.py` | `reasoning` field added end-to-end: `_DISTILL_JSON_SCHEMA` now has `reasoning: {type: string, maxLength: 500}` in properties + required; system prompt asks for it; `store_procedural(reasoning: str = "")` extended, wired through `_store()` → `execute_store()` → `build_unified_metadata()`. Injector's `meta.get("reasoning", "")` now finds populated data. |

### P1 (4 bugs — dedup, tags, docstring, singleton)

| # | File | Fix |
|---|------|-----|
| 6 | `memory_backend/atomic_extract.py` | Dedup: `min_score=0.0` (fetch all, post-filter) → `min_score=0.92` (let ChromaDB filter at the source — simpler + faster). |
| 7 | `memory_backend/atomic_extract.py` | Tag prefix: `type:{fact['type']}` → `category:{fact['type']}` (canonical — `type:` is not in `VALID_TAG_PREFIXES`). |
| 8 | `memory_backend/meta_learning.py` | Docstring: "UNIFICATION STATUS: Partial" → "Complete" (the injector split-brain is now actually fixed). |
| 9 | `tools/memory_ops/actions/update.py` | `_get_audit_db()` singleton: was creating a new SQLite connection on every call (docstring said "Singleton per process" — it wasn't). Now uses module-level `_audit_conn` + `_audit_lock` with double-checked locking; removed 3 `audit_conn.close()` calls that would break the shared connection. |

### P2 (3 bugs — documentation, field rename)

| # | File | Fix |
|---|------|-----|
| 10 | `sleep_learn/janitor.py` | Comment clarified: Janitor Bypass is at the ACTION layer (`tools/memory_ops/actions/janitor.py` lazy-imports), not the function layer. |
| 11 | `sleep_learn/migrate.py` | Merge semantics documented: confidence=MAX (not average), recall_count NOT updated, last_accessed_at NOT updated, provenance_count recomputed from `source_trace_ids` union — all deliberate choices, not bugs. |
| 12 | `memory_backend/read_ops.py` | Field rename: `"trace_id"` → `"source_trace_id"` in recall results (was confusing — it's the memory's ORIGIN trace, not the current query's trace; matches schema's `source_trace_ids` field naming). |

See [memory/CHANGELOG.md](memory/CHANGELOG.md) and [sleep_learn/CHANGELOG.md](sleep_learn/CHANGELOG.md) for full version-history details.

*Last updated: 2026-07-18 (v1.2 post-merge cleanup: 12 bugs fixed). See subfiles for detailed documentation.*
