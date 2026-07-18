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

*Last updated: 2026-07-18 (v1.1 observability fix). See subfiles for detailed documentation.*
