# 🧠 Memory Backend

The memory backend is a **three-collection ChromaDB vector store** with decay scoring, query rewriting, thread-safe write operations, and two learning subsystems. It provides persistent knowledge storage across **episodic** (events), **semantic** (facts), and **procedural** (skills) collections.

**Key characteristics:**
- **Three collections** — Episodic (what happened), semantic (what you know), procedural (how to do it)
- **Four-layer dedup** — Hash guard → outer vector → inner vector (inside lock) → procedural reinforcement
- **Decay scoring** — Memories fade over time; procedural memories bypass decay entirely
- **Two learning systems** — Inline meta-learning (fast) + background sleep-learning (deep). See [SLEEP_LEARN.md](SLEEP_LEARN.md) for the background daemon.
- **Unified rule schema (v1.2)** — Both procedural writers conform to `core/memory_backend/rule_schema.py`. See [unified schema docs](memory/API.md#-unified-rule-schema-v12--l3-contract).
- **Thread-safe writes** — `threading.Lock()` per collection with cancellation guards
- **Context budgeting** — Cognitive priority-based message trimming before LLM calls
- **Autonomous maintenance** — Diversity enforcer, janitor daemon, eviction engine

---

## 🚀 Quick Start

```python
from core.memory_engine import memory

# Store episodic (what happened)
memory.store_episodic(
    text="Fixed bug in memory.py -- missing colon after def",
    importance=8, goal="fix scraping bug", outcome="success",
    tools_used="python,git", trace_id="abc123"
)

# Store semantic (what you know)
memory.store_semantic(
    text="ChromaDB get_or_create_collection is idempotent",
    importance=7, tags="chromadb,startup"
)

# Store procedural (how to do it)
memory.store_procedural(
    text="To fix SyntaxError: always check line N-2 for unclosed bracket",
    importance=9, tags="syntax,debug"
)

# Recall (searches all collections by default)
results = memory.recall("how to fix syntax errors", top_k=5)
for r in results:
    print(r["text"], r["score"])
```

---

## ⚙️ Configuration

### Environment Variables

| Env Variable | Default | Description |
|--------------|---------|-------------|
| `MEMORY_ROOT` | `{agent_root}/memory_db` | ChromaDB and SQLite storage root |
| `MEMORY_DELETE_THRESHOLD` | `0.4` | Decay score below which memories are pruned |
| `MEMORY_DECAY_DAYS` | `30` | Days until decay floor (0.3) is reached |
| `MEMORY_TOP_K` | `5` | Default results per recall query |
| `MAX_MEMORY_BYTES` | `50000` | Max bytes per memory entry (50KB) |
| `MAX_TAGS_PER_ENTRY` | `6` | Max tags per memory entry |
| `MAX_TAG_LENGTH` | `50` | Max characters per tag |
| `EMBED_MODEL` | `all-MiniLM-L6-v2` | ChromaDB embedding model |

### Sleep & Learn Configuration

| Env Variable | Default | Description |
|--------------|---------|-------------|
| `SLEEP_LEARN_ENABLED` | `true` | Toggle the entire daemon |
| `SLEEP_LEARN_IDLE_THRESHOLD_SEC` | `3600` (1h) | Minimum idle time before background learning |
| `SLEEP_LEARN_MIN_RULE_WORDS` | `10` | Minimum words per extracted rule |
| `SLEEP_LEARN_MAX_DAILY_DISTILLATIONS` | `20` | Max distillation runs per day |
| `SLEEP_LEARN_INJECT_ENABLED` | `true` | Kill switch for rule injection |
| `SLEEP_LEARN_MIN_CONFIDENCE` | `0.8` | Minimum confidence for rule extraction |
| `SLEEP_LEARN_MAX_INJECTED_RULES` | `3` | Max rules injected into Planner prompt |

---

## 📂 Documentation

| File | Description |
|------|-------------|
| [ARCHITECTURE.md](memory/ARCHITECTURE.md) | Module tree, design decisions, data flows, dedup layers, scoring, thread safety, learning systems, maintenance |
| [API.md](memory/API.md) | Backend API reference — write ops, read ops, maintenance ops, parameter tables |
| [CHANGELOG.md](memory/CHANGELOG.md) | Breaking changes, version history, roadmap (completed, in-progress, deferred) |
| [INSTRUCTIONS.md](memory/INSTRUCTIONS.md) | AI editing rules — NEVER DO, ALWAYS DO, anti-patterns, hard constraints |

---

---

## 🔧 v1.1 Observability Fix (2026-07-18)

Three files fixed:
- **`core/memory_backend/janitor.py`** — `archive_old_episodes()` was using `tracer.error("janitor", ...)` with a literal string `trace_id`. Now uses `_tid = tracer.new_trace("janitor", ...)`.
- **`core/memory_backend/maintenance.py`** — 6 instances of `tracer.error("", "maintenance", ...)` (empty string `trace_id`) across 4 functions (`execute_delete`, `execute_prune`, `execute_summarize`, `execute_stats`). Each function now uses `_tid = generate_trace_id()` (NOT `tracer.new_trace()` — the side effects of `new_trace` — file I/O, stderr print, `_TraceStore` insert — interfered with ChromaDB query timing in `test_hash_cache_syncs_on_delete`, causing the just-stored memory to not be found → `KeyError: 'count'`). `generate_trace_id()` returns a unique 12-char hex ID with ZERO side effects. These functions only call `tracer.error()`, so a full trace record isn't needed. `execute_summarize` uses the caller-provided `trace_id` parameter if available.
- **`core/memory_backend/meta_learning.py`** — `run_forever()` daemon loop was using `tracer.step("daemon", ...)` per cycle. Now creates one trace per cycle via `_tid = tracer.new_trace("meta_learning", ...)`.

See [observability/CHANGELOG.md](observability/CHANGELOG.md) for details.

*Last updated: 2026-07-18 (v1.1 observability fix + v1.4 maintenance generate_trace_id refinement). See subfiles for detailed documentation.*
