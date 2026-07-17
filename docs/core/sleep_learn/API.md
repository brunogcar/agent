<- Back to [Sleep & Learn Overview](../SLEEP_LEARN.md)

# 📝 API Reference

## 🔧 API Overview

The Sleep & Learn daemon exposes public functions through `core/sleep_learn/__init__.py` for background learning, rule injection, and feedback processing.

---

## ⚠️ Breaking Changes (pre-v1.0)

| Old | New | Migration |
|-----|-----|-----------|
| `core/memory.py` import in injector | `core/memory_engine.py` | `from core.memory_engine import memory` |
| `process_pending_feedback()` | `process_feedback()` | Function renamed to match actual implementation |
| `distill_rules(traces: list)` | `distill_observation(observation: dict)` | Single-observation distillation, not batch |
| `filter_new_rules(rules: list)` | `is_quality_rule(rule_text: str)` | Single-rule validation with safety gates |
| `check_contradiction(rule, existing)` | Not implemented | No standalone contradiction checker; handled by `diversity_maintenance()` in `memory_backend/maintenance.py` |
| `store_rule(rule: dict)` | `save_rule(rule_text, source_memory_id, confidence)` | Direct storage API, not dict-based |
| `memory_sleep.remember()` | `save_rule()` via isolated ChromaDB client | No `memory_sleep` facade exists; storage uses direct `collection.add()` |
| 15s distiller timeout | 60s timeout | `llm.complete(timeout=60)` — intentional for local model stability |
| `SLEEP_MIN_IDLE_SECONDS` | `SLEEP_LEARN_IDLE_THRESHOLD_SEC` | Env var renamed; default 3600s (1h), not 7200s |
| `SLEEP_CONFIDENCE_THRESHOLD` (0.6) | `SLEEP_LEARN_MIN_CONFIDENCE` (0.8) | Higher threshold for background learning |

---

## 📦 Components

### 1. Daemon (`daemon.py`)

```python
def start_background_daemon() -> None:
    """Starts the Sleep & Learn daemon in a background thread."""
```

- Runs `process_feedback()` immediately at startup
- Checks every hour for midnight (hour 0, new date)
- Runs in a `daemon=True` thread — dies with the main process
- **v1.0: Idle detection added** — gates on `tracker.try_acquire_background_slot(min_idle_seconds=300)`

---

### 2. Logger (`logger.py`)

```python
def log_event(event_data: dict) -> None:
    """Appends a structured event to logs/sleep_learn/sleep_learn_YYYYMMDD.jsonl"""
```

- Thread-safe via `threading.Lock()`
- Auto-adds `_timestamp_utc` if missing
- Writes to `cfg.sleep_learn_log_path / "sleep_learn_YYYYMMDD.jsonl"`

---

### 3. Feedback Processor (`feedback.py`)

```python
def process_feedback() -> dict:
    """
    Matches pending injections with finished traces from agent logs.
    Updates confidence scores, recall counts, and archives processed injections.
    Returns: {"processed": N, "boosted": N, "penalized": N, "purged": N, "errors": N}
    """
```

| Outcome | Action | Confidence Effect |
|---------|--------|-------------------|
| **Success after rule applied** | Boost rule confidence | `+0.1` (capped at 1.0) |
| **Failure after rule applied** | Penalize rule confidence | `-0.2` (or `-0.3` for ignored impact warnings) |
| **Infrastructure failure** | Neutral — no change | `0` (timeout, connection, rate limit, etc.) |
| **Confidence < 0.3** | Auto-purge rule | Deleted from `procedural_meta` |

**Key behaviors:**
- Reads `logs/sleep_learn/injections.jsonl` for pending rule injections
- Scans `logs/agent_YYYYMMDD.jsonl` for `trace_finish` events
- Matches by `trace_id` — links injections to outcomes
- Handles Windows file locks gracefully (skips locked files, retries next cycle)
- Updates `recall_count` and `last_accessed_at` for all injected rules
- Rewrites injections log without processed entries

---

### 4. Distiller (`distiller.py`)

```python
def distill_observation(observation: dict) -> dict:
    """
    Takes a single observation and attempts to distill a rule.
    Uses llm.complete(role="executor", json_mode=True, timeout=60).
    Returns: {"status": "success", "rule_id": "...", "rule_preview": "..."}
             or {"status": "rejected", "reason": "..."}
             or {"status": "error", "reason": "..."}
    """
```

**LLM Call:**
```python
result = llm.complete(
    role="executor",
    system=DISTILLATION_SYSTEM_PROMPT,
    user=f"Analyze this observation and extract a procedural rule:\n\n{obs_text}",
    json_mode=True,
    timeout=60,
    max_tokens=256
)
```

**Output Schema:**
```json
{
    "rule": "When ChromaDB returns empty results after compaction, check if the collection was recreated without re-seeding",
    "confidence": 0.75
}
```

**Quality gates:**
1. Empty observation → skip
2. LLM failure → error
3. Invalid JSON schema → failed
4. `is_quality_rule()` rejection → rejected
5. `save_rule()` storage → success

> **Timeout note:** The 60s timeout is intentional for local model stability. The distiller uses `llm.complete()` which respects all global rate limits, budgets, and circuit breakers.

---

### 5. Filters (`filters.py`)

```python
def is_quality_rule(rule_text: str) -> tuple[bool, str]:
    """
    Validates a distilled rule.
    Returns (is_valid, reason).
    """
```

| Filter | Rejects | Example |
|--------|---------|---------|
| **Empty** | Empty or whitespace-only strings | `""` |
| **Safety** | Dangerous operations | `os.system`, `subprocess.call`, `eval(`, `exec(`, `rm -rf`, `sudo`, `chmod 777`, `drop table` |
| **Generic** | Common advice patterns | `"be careful"`, `"always remember"`, `"think step by step"`, `"make sure to"` |
| **Too short** | Rules < `SLEEP_LEARN_MIN_RULE_WORDS` (default 10) | `"Use try/except"` |

---

### 6. Storage (`storage.py`)

```python
def save_rule(rule_text: str, source_memory_id: str, confidence: float = 0.8) -> str:
    """
    Saves a validated rule to the isolated collection.
    Returns the generated rule_id (SHA256 hex, 16 chars).
    """
```

**Physical Isolation:** The `procedural_meta` collection lives in `memory_root/sleep_learn_db/` — a completely separate ChromaDB instance from the main `memory_db/`.

**v1.0: `save_rule()` now uses `build_unified_metadata()` from `core/memory_backend/rule_schema.py`.** The fields below are backward-compat; the unified schema adds `importance`, `version`, `schema_version`, `provenance_count`, etc.

**Metadata stored (backward-compat view):**
```python
{
    "source_memory_id": "...",
    "confidence_score": 0.8,
    "created_at": 1234567890,
    "last_accessed_at": 1234567890,
    "recall_count": 0,
    "source": "sleep_learn_daemon",
    "phase": "2_active_distillation"
}
```

**Deduplication:** Exact duplicate check via `collection.get(ids=[rule_id])` before insert. Rule ID is `SHA256(rule_text)[:16]`.

---

### 7. Injector (`injector.py`)

```python
def get_relevant_rules(query: str, k: int = 3) -> list[dict]:
    """
    Queries the procedural_meta collection for rules relevant to the current task.
    Falls back to main memory's procedural collection for split-brain compatibility.
    """

def inject_rules_into_prompt(goal: str, system_prompt: str, trace_id: str = "") -> str:
    """
    Retrieves relevant rules for the goal and appends them to the system prompt.
    If injection is disabled or no rules are found, returns the original prompt.
    """
```

**Split-brain fallback:** The injector queries both the isolated `procedural_meta` collection AND the main memory's `procedural` collection. This ensures rules learned by `meta_learning.py` are visible even if the sleep-learn daemon has not processed them yet.

**v1.0 (Commit 4): Split-brain fallback replaced with unified read.** The injector reads from the main `procedural` collection using the `confidence` field (unified schema). The legacy dual-collection query path is removed; `procedural_meta` is dropped after migration.

**Deduplication:** Uses `seen_ids` set for O(n) dedup (not O(n²) scan).

**Confidence scale normalization:** Main memory importance (1–10) is clamped to `[0, 1]` for unified scoring.

**Kill switch:** If `SLEEP_LEARN_INJECT_ENABLED=false`, returns the base prompt unchanged.

---

### 8. Sweeper (`sweeper.py`)

```python
def sweep_recent_observations(hours: int = 1) -> list[dict]:
    """
    Phase 1: Returns structured observation candidates without modifying state.
    TODO Phase 2: Integrate with core.memory_backend or core.tracer for real events.
    """
```

- Currently returns a heartbeat observation only
- No LLM calls, no ChromaDB writes
- Planned for Phase 2: integrate with tracer to gather errors, retries, corrections

---

### 9. Janitor (`janitor.py`)

```python
def purge_stale_rules() -> dict:
    """
    Deletes rules older than cfg.purge_age_days OR with confidence < 0.5.
    Never purges rules that have been recalled (recall_count > 0).
    Conservative fallback: 180 days for never-recalled rules.
    Returns: {"purged": N, "error": str|None}
    """
```

- Uses lazy singleton ChromaDB client (consistent with `storage.py`/`feedback.py`)
- `get_or_create_collection()` guard for first-boot safety
- Called by `tools/memory.py` janitor action alongside `archive_old_episodes()`

---

## 📡 API Reference Table

| Function | Module | Signature | Description |
|----------|--------|-----------|-------------|
| `start_background_daemon()` | `daemon.py` | `() -> None` | Start the scheduler |
| `process_feedback()` | `feedback.py` | `() -> dict` | Process all pending feedback entries |
| `update_rule_confidence()` | `feedback.py` | `(rule_id, success, penalty_override) -> dict` | Update a single rule's confidence |
| `_update_recall_counts()` | `feedback.py` | `(rule_counts) -> None` | Batch update recall_count for injected rules |
| `distill_observation()` | `distiller.py` | `(observation: dict) -> dict` | Extract a rule from a single observation |
| `is_quality_rule()` | `filters.py` | `(rule_text: str) -> tuple[bool, str]` | Validate a single rule |
| `save_rule()` | `storage.py` | `(rule_text, source_memory_id, confidence=0.8) -> str` | Write validated rule to `procedural_meta` |
| `get_collection_stats()` | `storage.py` | `() -> dict` | Return count and name of learned rules collection |
| `get_relevant_rules()` | `injector.py` | `(query, k=3) -> list[dict]` | Query both procedural collections |
| `inject_rules_into_prompt()` | `injector.py` | `(goal, system_prompt, trace_id="") -> str` | Merge rules into Planner prompt |
| `sweep_recent_observations()` | `sweeper.py` | `(hours=1) -> list[dict]` | Gather high-signal events (Phase 1: heartbeat only) |
| `purge_stale_rules()` | `janitor.py` | `() -> dict` | Delete old or low-confidence rules |

---

*Last updated: 2026-07-17. See [ARCHITECTURE.md](ARCHITECTURE.md) for file maps and design decisions, [CHANGELOG.md](CHANGELOG.md) for version history, [INSTRUCTIONS.md](INSTRUCTIONS.md) for AI editing rules.*
