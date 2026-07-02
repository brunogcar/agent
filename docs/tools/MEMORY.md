# 🧠 Memory Tool

The `memory()` tool is the **LLM-facing interface** to the agent's persistent memory backend. It wraps `core.memory_engine.MemoryStore` in a single `@tool` function with if/elif dispatch, providing the LLM with a unified API for storing, recalling, and maintaining memories across three collections.

**Key characteristics:**
- **Monolithic dispatch** — Single `memory(action, ...)` function with if/elif branching (pre-v1.0 pattern)
- **Lazy loading** — ChromaDB is only imported on first non-janitor call via `_mem()` closure
- **Janitor bypass** — `archive_old_episodes()` and `purge_stale_rules()` run without touching the memory store (avoids ChromaDB load)
- **Tag validation** — MED-05 compliant: XSS/injection prevention, length limits, character whitelist
- **Result compression** — All responses pass through `compress_result()` to prevent context window bloat
- **Trace ID threading** — `trace_id` propagated through all action results for observability

---

## ⚠️ Breaking Changes (pre-v1.0)

| Old | New | Migration |
|-----|-----|-----------|
| `core/memory.py` import | `core/memory_engine.py` | Internal change — no LLM-facing impact |
| `tools/memory_tool.py` | `tools/memory/` (planned) | File will be renamed to `tools/memory.py` or split into `tools/memory_ops/` |
| Monolithic if/elif dispatch | `@meta_tool` + `@register_action` auto-discovery | Planned v1.0 refactor — same API surface |
| `tests/tools/memory_tool/` | `tests/tools/memory/` | Test folder rename planned |

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

# Run maintenance
memory(action="janitor")
```

---

## 🏗️ Architecture

```text
tools/memory_tool.py          # @tool facade — monolithic dispatch (pre-v1.0)
├── _mem()                    # Lazy import: from core.memory_engine import memory
├── _validate_tags()          # MED-05 tag validation (XSS/injection prevention)
└── memory(action, ...)       # if/elif dispatch to 7 actions
    ├── store → store.store()
    ├── recall → store.recall()
    ├── delete → store.delete()
    ├── prune → store.prune()
    ├── summarize → store.summarize()
    ├── stats → store.stats()
    └── janitor → archive_old_episodes() + purge_stale_rules() (bypasses store)

core/memory_engine.py         # Thin facade — re-exports MemoryStore singleton
core/memory_backend/          # Implementation (see docs/core/MEMORY.md)
```

### Dispatch Flow

```mermaid
graph TD
    A["memory(action, ...)") --> B{"action?"}
    B -->|"janitor"| C["archive_old_episodes()\npurge_stale_rules()\nNO store load"]
    B -->|other| D["_mem() → lazy load store"]
    D --> E{"action?"}
    E -->|store| F["_validate_tags()\nstore.store()"]
    E -->|recall| G["_validate_tags(tags_filter)\nstore.recall()"]
    E -->|delete| H["store.delete()"]
    E -->|prune| I["store.prune()"]
    E -->|summarize| J["store.summarize()"]
    E -->|stats| K["store.stats()"]
    E -->|unknown| L["fail('Unknown action ...')"]
    C --> M["compress_result(ok({...}))"]
    F --> M
    G --> M
    H --> M
    I --> M
    J --> M
    K --> M
    L --> N["fail('Unknown action ...')"]
```

### Lazy Loading Pattern

```python
def _mem():
    """Lazy import of memory store -- avoids slow chromadb load at startup."""
    from core.memory_engine import memory as _memory
    return _memory
```

The `janitor` action is handled **before** `_mem()` is called. This means:
- `memory(action="janitor")` never imports ChromaDB
- Server startup is fast even if ChromaDB is not installed
- The janitor operates on the filesystem (JSONL logs) and isolated ChromaDB instance, not the main store

---

## 📝 Tool Signature

```python
@tool
def memory(
    action: str,
    text: str = "",
    memory_type: str = "semantic",
    importance: int = 5,
    tags: str = "",
    trace_id: str = "",
    goal: str = "",
    outcome: str = "unknown",
    tools_used: str = "",
    source: str = "",
    query: str = "",
    top_k: int = 5,
    collections: list = None,
    min_score: float = 0.5,
    tags_filter: str = "",
    threshold: float = 0.0,
    confirm_ids: list = None,
    max_age_days: int = 30,
    min_importance: int = 3,
    dry_run: bool = True,
) -> dict:
    """Memory tool -- store, recall, and manage agent memories."""
```

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `action` | `str` | **Yes** | One of: `store`, `recall`, `delete`, `prune`, `summarize`, `stats`, `janitor` |
| `text` | `str` | No | Memory content. **Required** for `store`. |
| `memory_type` | `str` | No | Target collection: `episodic` / `semantic` / `procedural`. Default: `semantic`. |
| `importance` | `int` | No | Base score 1–10. Default: `5`. Higher = slower decay. |
| `tags` | `str` | No | Comma-separated tags. Max `cfg.max_tags_per_entry`. |
| `trace_id` | `str` | No | Trace identifier for logging and correlation. |
| `goal` | `str` | No | What was being attempted (episodic/procedural). |
| `outcome` | `str` | No | `success` / `failure` / `partial` / `unknown`. Default: `unknown`. |
| `tools_used` | `str` | No | Comma-separated tool names (episodic). |
| `source` | `str` | No | Source attribution (semantic), e.g. URL. |
| `query` | `str` | No | Search query. **Required** for `recall` and `delete`. |
| `top_k` | `int` | No | Max results for `recall`. Default: `5`. |
| `collections` | `list` | No | Filter to specific collections. Default: all. |
| `min_score` | `float` | No | Minimum decay score for `recall`. Default: `0.5`. |
| `tags_filter` | `str` | No | Comma-separated — only return memories with ANY of these tags. |
| `threshold` | `float` | No | Similarity threshold for `delete`. |
| `confirm_ids` | `list` | No | Specific IDs to delete (bypasses similarity search). |
| `max_age_days` | `int` | No | For `prune`: max age before removal. Default: `30`. |
| `min_importance` | `int` | No | For `prune`: minimum importance to keep. Default: `3`. |
| `dry_run` | `bool` | No | For `prune`: preview deletions without executing. Default: `True`. |

---

## ⚡ Actions

### `store` — Save a Memory

Stores text into one of three typed collections with deduplication, decay scoring, and tag validation.

**Validation:**
- Missing `text` → `fail("text is required for store")`
- `importance` outside 1–10 → `fail("importance must be 1-10, got ...")`
- Text exceeds `cfg.memory_max_entry_bytes` → `fail("text is ... bytes -- exceeds ...")`
- Invalid tags → `fail("Tags cannot contain: ...")` or `fail("Tag contains invalid characters: ...")`

**Typed helpers in backend:**
- `memory_type="episodic"` → `store.store_episodic(...)` — task runs, outcomes
- `memory_type="semantic"` → `store.store_semantic(...)` — facts, research
- `memory_type="procedural"` → `store.store_procedural(...)` — fix patterns, solutions

**Return:**
```json
{
  "status": "success",
  "data": {
    "status": "stored",
    "id": "uuid",
    "trace_id": "abc123"
  }
}
```

Or if duplicate detected:
```json
{
  "status": "success",
  "data": {
    "status": "skipped_duplicate",
    "reason": "semantic_match",
    "directive": "This knowledge is already in memory. Do not retry.",
    "matched_snippet": "First 200 chars...",
    "existing_id": "uuid",
    "retry_recommended": false
  }
}
```

### `recall` — Semantic Search

Searches across memory collections using ChromaDB vector similarity, ranked by decay score.

**Validation:**
- Missing `query` → `fail("query is required for recall")`
- Invalid `tags_filter` → `fail("Tags cannot contain: ...")`

**Return:**
```json
{
  "status": "success",
  "data": {
    "count": 3,
    "results": [
      {
        "text": "To fix SyntaxError: always check line N-2 for unclosed bracket",
        "collection": "procedural",
        "score": 0.95,
        "tags": ["syntax", "debug"],
        "metadata": {...},
        "id": "uuid"
      }
    ]
  }
}
```

### `delete` — Remove Memories

Removes memories by similarity query or explicit IDs.

**Validation:**
- Missing `query` → `fail("query is required for delete")`

**Return:** Deletion status payload from `store.delete()`.

### `prune` — Maintenance Cleanup

Removes stale or low-importance memories. Defaults to `dry_run=True` for safety.

**Return:** Prune statistics from `store.prune()`.

### `summarize` — Collection Summary

Generates an LLM summary of top memories across collections.

**Return:** Summary text from `store.summarize()`.

### `stats` — Collection Statistics

Returns counts for all collections without loading ChromaDB vectors.

**Return:**
```json
{
  "status": "success",
  "data": {
    "collections": {
      "episodic": {"count": 1234},
      "semantic": {"count": 567},
      "procedural": {"count": 89}
    },
    "total": 1890
  }
}
```

### `janitor` — Memory Compaction

Runs maintenance without loading the main memory store. This is the **fastest** memory action because it bypasses ChromaDB entirely.

**What it does:**
1. `archive_old_episodes()` — Move old episodic memories to `episodic_archive` collection
2. `purge_stale_rules()` — Delete low-confidence rules from the isolated `procedural_meta` collection

**Return:**
```json
{
  "status": "success",
  "data": {
    "episodic_archived": 42,
    "rules_purged": 7,
    "errors": []
  }
}
```

---

## 🔒 Tag Validation (MED-05)

All tag inputs (`tags` for `store`, `tags_filter` for `recall`) pass through `_validate_tags()`:

| Rule | Enforcement |
|------|-------------|
| **Dangerous characters** | `< > " ' \` \|` — immediate rejection |
| **Max tags per entry** | `cfg.max_tags_per_entry` (default 6) for `store`; 10 for `tags_filter` |
| **Max tag length** | `cfg.max_tag_length` (default 50) |
| **Must start with** | Letter `[a-zA-Z]` |
| **Allowed characters** | Letters, numbers, hyphens, dots, underscores, spaces |
| **Pattern** | `^[a-zA-Z][a-zA-Z0-9_.\\s-]*$` |

```python
def _validate_tags(tags: str, max_count: int = 6) -> tuple[bool, str]:
    """
    Returns (is_valid, error_message).
    Empty string is valid (no tags).
    """
```

---

## 📊 Result Compression

All action results pass through `compress_result()` from `core.utils`:

- Large `text` fields are truncated with artifact recovery
- Full content saved to `workspace/.artifacts/`
- Structured metadata always preserved
- `trace_id` threaded through for observability

---

## ⚙️ Configuration

| Env Variable | Default | Description |
|--------------|---------|-------------|
| `MEMORY_MAX_ENTRY_BYTES` | `50000` | Max bytes per memory entry (50KB) |
| `MAX_TAGS_PER_ENTRY` | `6` | Max tags per memory entry |
| `MAX_TAG_LENGTH` | `50` | Max characters per tag |

---

## 🧪 Testing

```powershell
# Run all memory tool tests (current folder: tests/tools/memory_tool/)
D:\mcp\agent\venv\Scripts\pytest.exe tests/tools/memory_tool/ -v -W error --tb=short
```

**Current test layout:**
```text
tests/tools/memory_tool/          # Will be renamed to tests/tools/memory/
├── __init__.py
├── test_memory_tool.py           # Main tool tests (monolithic dispatch)
└── test_memory_tool_janitor.py   # Janitor-specific tests
```

**Planned v1.0 test layout:**
```text
tests/tools/memory/               # Renamed folder
├── conftest.py                   # Shared fixtures: reset_memory_state, mock_store
├── test_facade.py                # @meta_tool metadata, action Literal, unknown action
├── test_registry.py              # DISPATCH, @register_action, duplicate guard
├── test_store.py                 # store action: validation, dedup, size limits
├── test_recall.py                # recall action: search, filtering, tags
├── test_delete.py                # delete action: similarity, confirm_ids
├── test_prune.py                 # prune action: dry_run, age/importance filters
├── test_summarize.py             # summarize action
├── test_stats.py                 # stats action
├── test_janitor.py               # janitor action: bypass, archive, purge
└── test_tag_validation.py        # MED-05: XSS, length, character rules
```

**Mock strategy:**
- Patch `core.memory_engine.memory` with `MagicMock` for all unit tests
- Patch `core.memory_backend.janitor.archive_old_episodes` for janitor tests
- Patch `core.sleep_learn.janitor.purge_stale_rules` for janitor tests
- Patch `cfg.memory_max_entry_bytes` and `cfg.max_tags_per_entry` for validation tests

---

## 🗺️ Roadmap

### ✅ Completed

| Feature | Status | Notes |
|---------|--------|-------|
| Monolithic `memory(action, ...)` dispatch | ✅ pre-v1 | Single `@tool` function with if/elif branching |
| Lazy ChromaDB loading | ✅ pre-v1 | `_mem()` closure; janitor bypasses store entirely |
| 7 actions (store/recall/delete/prune/summarize/stats/janitor) | ✅ pre-v1 | All wired to `core.memory_engine.MemoryStore` |
| Tag validation (MED-05) | ✅ pre-v1 | XSS/injection prevention, length limits, character whitelist |
| Result compression | ✅ pre-v1 | `compress_result()` on all outputs |
| Trace ID threading | ✅ pre-v1 | Propagated through all action results |
| Janitor bypass optimization | ✅ pre-v1 | `archive_old_episodes()` + `purge_stale_rules()` without store load |

### 🔄 In Progress / Next Up

| Feature | Notes | Priority |
|---------|-------|----------|
| `@meta_tool` + `@register_action` auto-discovery | `Literal` enum, dynamic docstring, no central wiring. Follows git/file/cli/tavily pattern. | P0 |
| Un-multiplex to `memory_ops/actions/*.py` | Atomic action files: store, recall, delete, prune, summarize, stats, janitor | P0 |
| Rename `tools/memory_tool.py` → `tools/memory.py` | Align with `_ops`/`_backend` naming convention | P0 |
| Rename test folder `memory_tool/` → `memory/` | Match new tool name | P0 |
| Add `conftest.py` with shared fixtures | `reset_memory_state`, `mock_store`, `mock_janitor` | P0 |
| Split tests into per-action files | `test_store.py`, `test_recall.py`, etc. | P1 |
| Add `test_tag_validation.py` | Dedicated MED-05 coverage | P1 |
| Add `test_facade.py` | `@meta_tool` metadata, action Literal, unknown action guard | P1 |
| Add `test_registry.py` | `DISPATCH` dict, `@register_action`, duplicate guard | P1 |

### 🚫 Deferred / Out of Scope

| # | Feature | Why Deferred | Priority |
|---|---------|------------|----------|
| 1 | Streaming memory writes | ChromaDB does not support streaming inserts | Skip |
| 2 | Batch store action | Current `store` handles one entry; batch would require API change | Skip |
| 3 | Real-time memory sync | No multi-agent deployment currently | Skip |
| 4 | Custom embedding models | `all-MiniLM-L6-v2` is fast and accurate enough | Skip |
| 5 | Memory graph queries | Relationship tracking belongs in backend, not tool | Skip |
| 6 | Configurable action list | Hardcoded 7 actions cover all use cases | Skip |

---

## 🛡️ AI Agent Instructions

### NEVER DO
1. **Never add logic to `tools/memory_tool.py`** — Logic belongs in `core.memory_backend/` or `core.memory_engine`. The tool is a thin facade.
2. **Never remove the janitor bypass** — `archive_old_episodes()` and `purge_stale_rules()` must run without loading the memory store.
3. **Never skip `_validate_tags()`** — All tag inputs must pass MED-05 validation before reaching the backend.
4. **Never remove `compress_result()`** — All tool outputs must be compressed to prevent context window bloat.
5. **Never hardcode tag limits** — Use `cfg.max_tags_per_entry` and `cfg.max_tag_length`, not magic numbers.
6. **Never create `.bak` files** — Forbidden by project rules.
7. **Never rewrite entire files** — Surgical edits only. Preserve existing code exactly.
8. **Never add `**kwargs` to the `@tool` facade** — FastMCP schema breaks.
9. **Never print to stdout** — MCP stdio corruption. Return dicts only.
10. **Never skip `compileall` before `pytest`** — Catches syntax errors early.

### ALWAYS DO
11. **Always use `_mem()` for lazy loading** — Never import `core.memory_engine` at module level.
12. **Always handle `janitor` before `_mem()`** — Preserve the ChromaDB bypass optimization.
13. **Always thread `trace_id` through all results** — For observability and result correlation.
14. **Always validate `tags` and `tags_filter` with `_validate_tags()`** — MED-05 compliance is mandatory.
15. **Always return `fail()` with clear messages** — Unknown actions, missing params, validation errors.
16. **Always run `compileall` after editing tool files** — Verify syntax before running tests.
17. **Always run targeted tests (`tests/tools/memory_tool/`) after changes** — Current coverage before refactor.

---

## 🔗 Source Code Reference

| File | Purpose |
|------|---------|
| `tools/memory_tool.py` | `@tool` facade — monolithic dispatch (pre-v1.0) |
| `core/memory_engine.py` | Thin facade — re-exports `MemoryStore` singleton |
| `core/memory_backend/store.py` | `MemoryStore` class — collections, stats, write lock |
| `core/memory_backend/write_ops.py` | `execute_store()` — dedup pipeline |
| `core/memory_backend/read_ops.py` | `execute_recall()` — semantic search |
| `core/memory_backend/maintenance.py` | `execute_delete/prune/summarize/stats()` |
| `core/memory_backend/janitor.py` | `archive_old_episodes()` — episodic archival |
| `core/sleep_learn/janitor.py` | `purge_stale_rules()` — rule purging from isolated collection |
| `core/utils.py` | `compress_result()` — context window compression |
| `core/contracts.py` | `ok()`, `fail()` — standardized response format |
| `core/config.py` | `memory_max_entry_bytes`, `max_tags_per_entry`, `max_tag_length` |

---

*Last updated: July 2026. Tool signature and action behaviors reflect current `tools/memory_tool.py` source.*
