# 🧠 Memory Tool

The `memory()` tool is the **LLM-facing interface** to the agent\'s persistent memory backend. It wraps `core.memory_engine.MemoryStore` in a single `@tool` function with `@meta_tool` auto-discovery dispatch, providing the LLM with a unified API for storing, recalling, and managing memories across three collections.

**Key characteristics:**
- **Atomic action dispatch** — `@meta_tool` + `@register_action` auto-discovery (v1.0)
- **Lazy loading** — ChromaDB is only imported on first non-janitor call via `_mem()` in `helpers.py`
- **Janitor bypass** — `archive_old_episodes()` and `purge_stale_rules()` run without touching the memory store (avoids ChromaDB load)
- **Tag validation** — MED-05 compliant: XSS/injection prevention, length limits, character whitelist
- **Result compression** — Success responses pass through `compress_result()` to prevent context window bloat (v1.1: skipped for errors; v1.2: crash caught)
- **Trace ID threading** — `trace_id` propagated through all action results for observability
- **Fail-fast validation** — Invalid `memory_type` and empty `collections=[]` rejected at tool layer, not silently coerced
- **Facade exception handling** — v1.1: Handler exceptions caught and returned as structured `fail()` responses
- **Duration tracking** — v1.2: `duration_ms` included in all responses for performance monitoring
- **`update` action (v1.4)** — Modify a memory by ID without delete+re-create; tracks changes in a sidecar SQLite audit table (`memory_db/memory_audit.db`, `rule_history` table)
- **`export`/`import` actions (v1.4)** — JSONL backup/restore of collections; used by the `procedural_meta` → `procedural` migration
- **Group-aware `delete` by `source_doc_id` (v1.4)** — Delete all chunks sharing a UUID in one call (prevents orphaned fragments)
- **`extract` action (v1.5)** — Atomic fact extraction (`core/memory_backend/atomic_extract.py`)
- **`tags_required` (v1.5)** — AND-based tag filtering for precise procedural recall (complements the OR-based `tags_filter`)

---

## 🚀 Quick Start

```python
# Store an episodic memory
memory(
    action="store",
    memory_type="episodic",
    text="Fixed SyntaxError in tools/web.py -- missing colon after def",
    importance=8,
    goal="fix scraping bug",
    outcome="success",
    tools_used="python,git",
    trace_id="abc123"
)

# Recall procedural rules
memory(
    action="recall",
    query="how to fix syntax errors",
    collections=["procedural"],
    top_k=3
)

# Get formatted context for prompt injection
memory(
    action="recall_context",
    query="how to fix syntax errors",
    collections=["procedural"],
    top_k=3
)

# Run maintenance
memory(action="janitor")
```

---

## ⚙️ Configuration

| Env Variable | Default | Description |
|--------------|---------|-------------|
| `MEMORY_MAX_ENTRY_BYTES` | `50000` | Max bytes per memory entry (50KB) |
| `MAX_TAGS_PER_ENTRY` | `6` | Max tags per memory entry |
| `MAX_TAG_LENGTH` | `50` | Max characters per tag |

---

## 📂 Documentation

| File | Description |
|------|-------------|
| [ARCHITECTURE.md](memory/ARCHITECTURE.md) | Module tree, design decisions, dispatch flow, test coverage, source code reference |
| [API.md](memory/API.md) | Full tool signature, all actions, validation rules, error handling, security |
| [CHANGELOG.md](memory/CHANGELOG.md) | Breaking changes, version history, roadmap (completed, in-progress, deferred) |
| [INSTRUCTIONS.md](memory/INSTRUCTIONS.md) | AI editing rules — NEVER DO, ALWAYS DO, anti-patterns, hard constraints |

---

*Last updated: 2026-07-17. See subfiles for detailed documentation.*
