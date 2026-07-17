<- Back to [Memory Overview](../MEMORY.md)

# 📝 API Reference

## Tool Signature

```python
@tool
@meta_tool(DISPATCH.get("memory", {}), doc_sections=[...])
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
    # v1.3 — Chunking (store action only)
    chunk: bool = False,
    chunk_method: str = "token",
    chunk_size: int = 512,
) -> dict:
    '''Memory meta-tool — atomic actions.'''
```

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `action` | `Literal[...]` | **Yes** | One of: `store`, `recall`, `recall_context`, `delete`, `prune`, `summarize`, `stats`, `janitor`, `update`, `export`, `import`, `extract` |
| `text` | `str` | No | Memory content. **Required** for `store`. |
| `memory_type` | `str` | No | Target collection: `episodic` / `semantic` / `procedural`. Default: `semantic`. |
| `importance` | `int` | No | Base score 1–10. Default: `5`. Higher = slower decay. |
| `tags` | `str` | No | Comma-separated tags. Max `cfg.max_tags_per_entry`. Multi-word tags supported: `"my tag, another tag"`. |
| `trace_id` | `str` | No | Trace identifier for logging and correlation. |
| `goal` | `str` | No | What was being attempted (episodic/procedural). |
| `outcome` | `str` | No | `success` / `failure` / `partial` / `unknown`. Default: `unknown`. |
| `tools_used` | `str` | No | Comma-separated tool names (episodic). |
| `source` | `str` | No | Source attribution (semantic), e.g. URL. |
| `query` | `str` | No | Search query. **Required** for `recall`, `recall_context`. **Required** for `delete` unless `confirm_ids` provided. |
| `top_k` | `int` | No | Max results for `recall` / `recall_context`. Default: `5`. |
| `collections` | `list` | No | Filter to specific collections. Default: all. `[]` is **rejected**. Must be a **list**, not a string. |
| `min_score` | `float` | No | Minimum decay score for `recall`. Default: `0.5`. |
| `tags_filter` | `str` | No | Comma-separated — only return memories with ANY of these tags. **Not supported by `recall_context`**. |
| `threshold` | `float` | No | Similarity threshold for `delete`. Must be 0.0–1.0. `0.0` is preserved as `0.0`, not converted to `None`. |
| `confirm_ids` | `list` | No | Specific IDs to delete (bypasses similarity search). Must be a list. |
| `max_age_days` | `int` | No | For `prune`: max age before removal. Must be `>= 0`. Default: `30`. |
| `min_importance` | `int` | No | For `prune`: minimum importance to keep. Must be 1–10. Default: `3`. |
| `dry_run` | `bool` | No | For `prune`: preview deletions without executing. Default: `True`. |
| `chunk` | `bool` | No | **v1.3.** If `True`, `store` splits `text` via chonkie into N linked chunks. Each chunk is stored as a separate memory with shared `source_doc_id` metadata. Enables precise recall. Only `semantic` and `episodic` collections; `procedural` is rejected (reinforcement conflict). Default: `False`. |
| `chunk_method` | `str` | No | **v1.3.** One of `"token"` (chonkie `TokenChunker`) or `"sentence"` (`SentenceChunker`). Ignored when `chunk=False`. Default: `"token"`. |
| `chunk_size` | `int` | No | **v1.3.** Approximate tokens per chunk. Ignored when `chunk=False`. Default: `512`. |

---

## ⚡ Actions

### `store` — Save a Memory

Stores text into one of three typed collections with deduplication, decay scoring, and tag validation.

**Validation:**
- Missing `text` → `fail("text is required for store")`
- `importance` outside 1–10 → `fail("importance must be 1-10, got ...")`
- Text exceeds `cfg.memory_max_entry_bytes` → `fail("text is ... bytes -- exceeds ...")`
- Invalid tags → `fail("Tags cannot contain: ...")` or `fail("Tag contains invalid characters: ...")`
- Invalid `memory_type` → `fail("Invalid memory_type '...'. Must be one of: episodic, procedural, semantic")`
- Empty `collections=[]` → `fail("collections cannot be empty — omit or pass None for all")`
- Non-list `collections` → `fail("collections must be a list, got ...")`

**Note on `collections`:** The `store` action uses `memory_type` to determine the target collection (`episodic`, `semantic`, or `procedural`). The `collections` parameter is validated but ignored for `store`. This is by design — each memory entry belongs to exactly one typed collection.

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
        "trace_id": "abc123",
        "duration_ms": 45
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
    },
    "duration_ms": 12
}
```

### `store` with `chunk=True` — Chunked Store (v1.3)

When `chunk=True`, the input `text` is split into N chunks via chonkie (same integration as file tool v1.2). Each chunk is stored as a separate memory with shared `source_doc_id` metadata, enabling precise recall — the LLM gets the specific paragraph, not the whole document.

**Restrictions:**
- Only `semantic` and `episodic` collections support chunking
- `procedural` is **rejected** — the reinforcement feature (increment `reinforcement_count` on semantic match) is nonsensical for chunks
- Per-entry size limit (50KB) still applies to the **full text** before chunking

**How it works:**
1. Text is split via chonkie `TokenChunker` or `SentenceChunker`
2. All chunks share a `source_doc_id` (UUID) + carry `chunk_index` (0-based) and `chunk_count`
3. Chunks are batch-inserted in a single ChromaDB `col.add()` call (atomic)
4. Hash dedup only (exact match) — vector dedup is skipped (chunks from the same document would falsely trigger it)

**Examples:**
```python
# Token chunking (default) — 512 tokens per chunk
memory(action="store", text="very long document...", chunk=True)

# Sentence chunking — groups whole sentences
memory(action="store", text="research paper...", chunk=True, chunk_method="sentence", chunk_size=256)

# Episodic chunking — store a long event log as linked chunks
memory(action="store", text="long workflow trace...", memory_type="episodic", chunk=True)
```

**Return (chunked):**
```json
{
    "status": "success",
    "data": {
        "status": "stored",
        "source_doc_id": "uuid",
        "stored": 12,
        "skipped_duplicates": 0,
        "chunk_count": 12,
        "collection": "semantic"
    },
    "duration_ms": 340
}
```

**Recall returns chunk metadata (v1.3):** Every recall result now includes `source_doc_id`, `chunk_index`, `chunk_count`. Non-chunked memories return defaults (`""`, `None`, `0`).

```python
results = memory(action="recall", query="authentication patterns")
# Each result:
# {
#   "text": "...",
#   "source_doc_id": "uuid",   # "" for non-chunked
#   "chunk_index": 3,          # None for non-chunked
#   "chunk_count": 12,         # 0 for non-chunked
#   ...
# }
```

### `recall` — Semantic Search

Searches across memory collections using ChromaDB vector similarity, ranked by decay score.

**Validation:**
- Missing `query` → `fail("query is required for recall")`
- Invalid `tags_filter` → `fail("Tags cannot contain: ...")`
- Empty `collections=[]` → `fail("collections cannot be empty — omit or pass None for all")`
- Non-list `collections` → `fail("collections must be a list, got ...")`

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
    },
    "duration_ms": 23
}
```

### `recall_context` — Formatted Context for Prompt Injection *(NEW v1.0)*

Returns a pre-formatted string of top memories, not a JSON list. Use this when you need to inject memory context directly into a system prompt.

**Limitations:**
- `tags_filter` and `min_score` are **not supported**. The backend `execute_recall_context()` does not accept these parameters. Use `recall()` for filtered searches, then format manually if needed.
- v1.2: Passing `tags_filter` or `min_score != 0.5` returns a clear error instead of silently ignoring the parameter.

**Validation:**
- Missing `query` → `fail("query is required for recall_context")`
- Empty `collections=[]` → `fail("collections cannot be empty — omit or pass None for all")`
- Non-list `collections` → `fail("collections must be a list, got ...")`
- `tags_filter` provided → `fail("recall_context does not support tags_filter...")`
- `min_score` != 0.5 → `fail("recall_context does not support min_score...")`

**Return:**
```json
{
    "status": "success",
    "data": {
        "context": "1. [procedural] To fix SyntaxError...\n2. [semantic] ChromaDB supports..."
    },
    "duration_ms": 18
}
```

### `delete` — Remove Memories

Removes memories by similarity query or explicit IDs.

**Validation:**
- Missing `query` AND missing `confirm_ids` → `fail("query or confirm_ids is required for delete")`
- `confirm_ids` not a list → `fail("confirm_ids must be a list, got ...")`
- Empty `collections=[]` → `fail("collections cannot be empty — omit or pass None for all")`
- Non-list `collections` → `fail("collections must be a list, got ...")`
- `threshold` outside 0.0–1.0 → `fail("threshold must be between 0.0 and 1.0")`

**Note:** `threshold=0.0` is preserved as `0.0` and passed to the backend. It is **not** converted to `None`.

**Return:** Deletion status payload from `store.delete()`.

### `prune` — Maintenance Cleanup

Removes stale or low-importance memories. Defaults to `dry_run=True` for safety.

**Validation:**
- Empty `collections=[]` → `fail("collections cannot be empty — omit or pass None for all")`
- Non-list `collections` → `fail("collections must be a list, got ...")`
- `max_age_days < 0` → `fail("max_age_days must be >= 0")`
- `min_importance` outside 1–10 → `fail("min_importance must be 1-10")`

**Return:** Prune statistics from `store.prune()`.

### `summarize` — Collection Summary

Generates an LLM summary of top memories across collections.

**Validation:**
- Empty `collections=[]` → `fail("collections cannot be empty — omit or pass None for all")`
- Non-list `collections` → `fail("collections must be a list, got ...")`

**Return:** Summary text from `store.summarize()`.

### `stats` — Collection Statistics

Returns counts for all collections without loading ChromaDB vectors.

**Validation:**
- Empty `collections=[]` → `fail("collections cannot be empty — omit or pass None for all")`
- Non-list `collections` → `fail("collections must be a list, got ...")`

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
    },
    "duration_ms": 5
}
```

### `janitor` — Memory Compaction

Runs maintenance without loading the main memory store. This is the **fastest** memory action because it bypasses ChromaDB entirely.

**What it does:**
1. `archive_old_episodes()` — Move old episodic memories to `episodic_archive` collection
2. `purge_stale_rules()` — Delete low-confidence rules from the isolated `procedural_meta` collection

**Resilience:**
- v1.1: If either function raises an exception, the janitor catches it and continues
- v1.1: If either function returns a non-dict, the janitor handles it gracefully with a clear error
- v1.2: Errors are forced to strings to prevent JSON serialization failures

**Return:**
```json
{
    "status": "success",
    "data": {
        "episodic_archived": 42,
        "rules_purged": 7,
        "errors": []
    },
    "duration_ms": 8
}
```

---

### `update` (v1.4)

Modifies a memory by ID without delete+re-create. Tracks changes in a sidecar SQLite audit table.

```python
memory(action="update", id="abc123", fields={"importance": 8}, reason="reinforced after success")
```

**Parameters:** `id` (required), `fields` (dict, required), `reason` (required), `collection` (optional).

**Updatable fields:** `importance`, `confidence`, `tags`, `goal`, `outcome`, `reasoning`, `source`, `tools_used`, `enabled`.

**Audit log:** Changes written to `memory_db/memory_audit.db` (`rule_history` table) — append-only.

---

### `export` / `import` (v1.4)

JSONL backup/restore. Needed for the `procedural_meta` → `procedural` migration.

```python
memory(action="export", collections=["procedural"], output_path="backup.jsonl")
memory(action="import", input_path="backup.jsonl")
```

---

### `delete` with `source_doc_id` (v1.4)

Group-aware deletion — delete all chunks sharing a `source_doc_id`.

```python
memory(action="delete", source_doc_id="doc-uuid")
```

---

## 🔒 Tag Validation

All tag inputs (`tags` for `store`, `tags_filter` for `recall`) pass through `_validate_tags()`:

| Rule | Enforcement |
|------|-------------|
| **Dangerous characters** | `< > " ' \` \|` — immediate rejection |
| **Max tags per entry** | `cfg.max_tags_per_entry` (default 6) for `store`; 10 for `tags_filter` |
| **Max tag length** | `cfg.max_tag_length` (default 50) |
| **Must start with** | Letter `[a-zA-Z]` |
| **Allowed characters** | Letters, numbers, hyphens, dots, underscores, spaces |
| **Pattern** | `^[a-zA-Z][a-zA-Z0-9_.\s-]*$` |
| **Separator** | Comma `,` — multi-word tags supported: `"my tag, another tag"` |

```python
def _validate_tags(tags: str, max_count: int = 6) -> tuple[bool, str]:
    '''
    Returns (is_valid, error_message).
    Empty string is valid (no tags).
    '''
```

**[DESIGN] `_validate_tags()` uses different limits for store vs recall:**
- `store`: `cfg.max_tags_per_entry` (default 6) — strict, enforced at write time
- `recall tags_filter`: hardcoded 10 — relaxed, read-only query parameter
This is intentional. Do not "simplify" both to the same config value.

**[DESIGN] Tag splitting:** Tags are comma-separated. Multi-word tags are supported: `"my tag, another tag"` produces `["my tag", "another tag"]`. Do not pass space-separated tags — each comma defines a tag boundary.

---

## 📊 Result Compression

Success responses pass through `compress_result()` from `core.utils`:

- Large `text` fields are truncated with artifact recovery
- Full content saved to `workspace/.artifacts/`
- Structured metadata always preserved
- `trace_id` threaded through for observability

**[DESIGN] `compress_result()` is called in the facade, not individual actions.**
The facade applies it only to **success** responses (v1.1). Error responses are returned as-is without compression. v1.2: If `compress_result()` itself crashes, the facade returns a structured `fail()` instead of leaking the exception.

---

*Last updated: 2026-07-17. See [ARCHITECTURE.md](ARCHITECTURE.md) for file maps and design decisions, [CHANGELOG.md](CHANGELOG.md) for version history, [INSTRUCTIONS.md](INSTRUCTIONS.md) for AI editing rules.*
