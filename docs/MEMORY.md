# 🧠 Memory System Architecture

The memory system is a three-collection ChromaDB vector store with decay scoring, query rewriting, and thread-safe write operations. It provides persistent knowledge storage across episodic (events), semantic (facts), and procedural (skills) collections.

## 🏗️ Architecture Overview

### Three Collections

| Collection | Purpose | Use Cases | Default Dedup Threshold |
|------------|---------|-----------|------------------------|
| **episodic** | What happened | Task runs, workflow outcomes, errors, events | 0.05 (near-identical only) |
| **semantic** | What you know | Facts, research, domain knowledge, documentation | 0.12 (similar facts) |
| **procedural** | How to do it | Fix patterns, solutions, reusable approaches | 0.08 (similar patterns) |

### Memory Entry Schema

Every memory entry stores structured metadata in ChromaDB:

```python
{
    "text":       str,            # Main content
    "type":       str,            # episodic | semantic | procedural
    "importance": int,            # 1-10
    "tags":       str,            # Comma-separated
    "timestamp":  int,            # Unix epoch
    "trace_id":   str,            # Links to workflow that created it
    "goal":       str,            # What was being attempted
    "outcome":    str,            # success | failure | partial | unknown
    "tools_used": str,            # Comma-separated tool names
    "source":     str,            # Where knowledge came from
}
```

---

## ⏳ Decay Scoring

Memories fade naturally over time to prevent context pollution. The decay formula ensures old high-importance memories never fully disappear.

### Formula

```python
score = importance × max(0.3, 1 - age_days / DECAY_DAYS)
```

- **Fresh memory** (age=0): `score = importance × 1.0`
- **Aging memory**: Linear decay until floor
- **Floor**: `0.3` (old memories retain 30% of importance)

### Examples (importance=8, decay_days=30)

| Age | Decay Factor | Score | Notes |
|-----|--------------|-------|-------|
| 0 days | 1.0 | 8.0 | Fresh, full importance |
| 15 days | 0.5 | 4.0 | 50% decayed |
| 30 days | 0.3 | 2.4 | At floor |
| 60 days | 0.3 | 2.4 | Floor, does not go lower |

### Configuration

```ini
# .env
MEMORY_DECAY_DAYS=30              # Days until floor (0.3) is reached
MEMORY_DELETE_THRESHOLD=0.4       # Memories below this are pruned
MEMORY_TOP_K=5                    # Default results per recall query
```

---

## 🔒 Write-Only Lock Pattern (MED-01)

ChromaDB's internal locking is insufficient for concurrent multi-collection writes. The memory system uses a **Write-Only Lock** pattern to maximize throughput under read-heavy workloads.

### How It Works

1. **Dedup query runs WITHOUT lock** (best-effort, racing acceptable)
2. **Only the actual INSERT uses explicit lock** (critical section)
3. **Double-check locking** inside the lock catches rare TOCTOU races

### Performance Impact

- **30-50% throughput improvement** under concurrent read-heavy workloads
- Dedup failures are non-fatal (store anyway)
- Lock contention minimized to actual writes only

### Implementation

```python
# Outer dedup check (no lock, best-effort)
existing = col.query(query_texts=[text], n_results=1, include=["distances"])
if existing["distances"][0][0] < dedup_threshold:
    return {"status": "skipped_duplicate"}

# Lock only the critical section
with self._write_lock:
    # TOCTOU fix: Re-check inside lock
    existing_inner = col.query(query_texts=[text], n_results=1, include=["distances"])
    if existing_inner["distances"][0][0] < dedup_threshold:
        return {"status": "skipped_duplicate"}
    
    # Actual insert (protected)
    col.add(documents=[text], ids=[memory_id], metadatas={...})
```

---

## 🏷️ Tag Validation (MED-05)

Tag validation prevents injection/XSS attacks and ensures clean metadata. Validation is enforced in `tools/memory_tool.py` before passing to `core/memory.py`.

### Rules

- **Rejects dangerous chars**: `< > " ' \` |`
- **Max 6 tags** per entry
- **Max 50 chars** per tag
- **Must start with letter**
- **Allowed chars**: alphanumeric, hyphens, dots, spaces

### Examples

```python
# ✅ Valid
tags="chromadb,architecture,vector-search"
tags="mcp,tool,registration"

# ❌ Invalid
tags="<script>alert('xss')</script>"  # Dangerous chars
tags="a,b,c,d,e,f,g"                  # Too many tags (7)
tags="this-is-a-very-long-tag-name-that-exceeds-fifty-characters"  # Too long
tags="123invalid"                      # Must start with letter
```

---

## 🔍 Query Rewriting

Before hitting ChromaDB, queries are rewritten to improve recall accuracy. This is a lightweight, model-free transformation.

### Rules

1. **Strip filler words** that hurt semantic search
2. **Expand common abbreviations**
3. **Lowercase for consistency**
4. **Preserve question starters** ("how", "what", "why")

### Filler Words (Stripped)

```python
FILLERS = {
    "please", "tell me", "show me",
    "the", "a", "an", "in", "on", "at", "of", "for",
}
```

### Expansions

```python
EXPANSIONS = {
    "py": "python",
    "fn": "function",
    "db": "database",
    "chroma": "chromadb",
    "mem": "memory",
    "cfg": "config",
    "err": "error",
    "msg": "message",
    "repo": "repository",
    "dir": "directory",
}
```

### Examples

```python
# Original: "Please show me how to fix the chroma db import err"
# Rewritten: "how fix chromadb import error"

# Original: "What is the cfg for mem decay?"
# Rewritten: "what config memory decay"
```

---

## 🛡️ Protected Pruning

The `procedural` collection is **protected from automatic pruning** to preserve high-value "how-to" patterns.

### Automatic Pruning (Default Behavior)

```python
memory.prune(max_age_days=30, min_importance=3, dry_run=False)
# Automatically excludes COLLECTION_PROCEDURAL
# Only prunes episodic and semantic
```

### Manual Pruning (Explicit Request)

```python
memory.prune(
    max_age_days=30,
    min_importance=3,
    dry_run=False,
    collections=["procedural"]  # Explicit override
)
```

### Protected Tags

Memories tagged with `"summary"`, `"critical"`, or `"protected"` are never pruned, regardless of age or importance.

---

## 📚 API Reference

### Store Methods

#### `store_episodic(text, importance=5, tags="", trace_id="", goal="", outcome="unknown", tools_used="")`

Store an event or task outcome.

```python
memory.store_episodic(
    text="Fixed SyntaxError in memory.py by adding missing colon",
    importance=8,
    outcome="success",
    tools_used="autocode,git",
    trace_id="abc123"
)
```

#### `store_semantic(text, importance=5, tags="", trace_id="", source="")`

Store a fact or domain knowledge.

```python
memory.store_semantic(
    text="ChromaDB collections are isolated vector spaces",
    importance=7,
    tags="chromadb,architecture",
    source="docs.trychroma.com"
)
```

#### `store_procedural(text, importance=7, tags="", trace_id="", goal="", outcome="success")`

Store a reusable solution or fix pattern. Default importance is 7 (higher than other types).

```python
memory.store_procedural(
    text="To register a new MCP tool: decorate with @tool, no changes to server.py needed",
    importance=9,
    tags="mcp,tool,registration"
)
```

#### `store(text, memory_type="semantic", importance=5, tags="", ...)`

Generic store that routes to the correct typed collection.

```python
memory.store(
    text="Agent completed research workflow successfully",
    memory_type="episodic",
    importance=6,
    outcome="success"
)
```

---

### Recall Methods

#### `recall(query, top_k=None, collections=None, min_score=0.5, tags_filter="", trace_id="")`

Search memories semantically similar to query. Results ranked by decay score.

```python
# Search all collections
results = memory.recall("how to fix syntax errors", top_k=5)

# Search specific collection
results = memory.recall("ChromaDB", collections=["semantic"])

# Filter by tags
results = memory.recall("tool registration", tags_filter="mcp")

# Results format
[
    {
        "text": "To fix SyntaxError: always check line N-2 for unclosed bracket",
        "type": "procedural",
        "importance": 9,
        "score": 8.1,
        "distance": 0.12,
        "tags": "syntax,debug",
        "age_days": 2.3,
        "collection": "procedural"
    },
    ...
]
```

#### `recall_context(query, top_k=None, collections=None, trace_id="")`

Convenience wrapper that returns a formatted context string ready for LLM prompts.

```python
context = memory.recall_context("how to fix import errors", top_k=3)
# Returns:
# [procedural | score=8.1 | 0.3d ago] To fix SyntaxError: always check line N-2...
# [episodic | score=7.2 | 2.1d ago] Fixed SyntaxError in memory.py by adding...
```

---

### Delete Method

#### `delete(query, collections=None, threshold=None, confirm_ids=None)`

Delete memories within similarity threshold of query. Always returns candidates for preview before confirming.

```python
# Dry-run preview
result = memory.delete("old debug patterns", threshold=0.15)
# Returns: {"status": "awaiting_confirmation", "candidates": [...]}

# Confirm deletion
result = memory.delete(
    "old debug patterns",
    threshold=0.15,
    confirm_ids=["id1", "id2"]
)
# Returns: {"status": "deleted", "count": 2, "deleted": [...]}
```

---

### Prune Method

#### `prune(max_age_days=30, min_importance=3, dry_run=True, collections=None)`

Remove old, low-importance memories. Protected collection and tags are respected.

```python
# Preview what would be deleted
result = memory.prune(max_age_days=60, min_importance=2, dry_run=True)
# Returns: {"status": "dry_run", "would_delete": 15, "candidates": [...]}

# Actually delete
result = memory.prune(max_age_days=60, min_importance=2, dry_run=False)
# Returns: {"status": "pruned", "deleted": 15, "entries": [...]}
```

---

### Summarize Method

#### `summarize(collections=None, top_n=30, store_result=True, trace_id="")`

Summarize stored memories using the Planner model. Stores summary as high-importance semantic memory.

```python
result = memory.summarize(top_n=50, store_result=True)
# Returns: {
#     "status": "summarized",
#     "summary": "Agent has fixed 23 syntax errors, primarily in memory.py...",
#     "input_count": 50
# }
```

---

### Stats Method

#### `stats()`

Return counts and basic stats for each collection.

```python
result = memory.stats()
# Returns: {
#     "episodic": {"count": 142},
#     "semantic": {"count": 87},
#     "procedural": {"count": 34}
# }
```

---

## ⚙️ Configuration (`.env`)

```ini
# ── Memory Tuning ────────────────────────────────────────────────
MEMORY_DECAY_DAYS=30              # Days until decay floor (0.3) is reached
MEMORY_DELETE_THRESHOLD=0.4       # Memories below this score are pruned
MEMORY_TOP_K=5                    # Default results per recall query
MEMORY_MAX_ENTRY_BYTES=10000      # Max bytes per memory entry (10KB)

# ── Dedup Thresholds (cosine distance, lower = more strict) ─────
MEMORY_DEDUP_THRESHOLD=           # Global override (optional)
# If empty, uses per-collection defaults:
#   episodic:   0.05
#   semantic:   0.12
#   procedural: 0.08
```

---

## 🚨 ChromaDB Client Creation

The `_make_client()` function wraps ChromaDB initialization with a hard timeout to prevent startup hangs on slow/flaky storage.

### Timeout Protection

```python
def _make_client(timeout: int = 60):
    """Create ChromaDB client with hard timeout; fall back to degraded mode."""
    try:
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(_create)
            client = future.result(timeout=timeout)
        return client
    except concurrent.futures.TimeoutError:
        # Degraded fallback
        client = chromadb.PersistentClient(path=..., allow_reset=True)
        return client
```

### Degraded Mode

If ChromaDB creation times out or fails, the system attempts a degraded reconnect with `allow_reset=True`. This prevents complete startup failure but may lose existing memories.

---

## ⚠️ AI Agent Instructions for Memory Operations

If you are an AI assistant modifying `core/memory.py` or `tools/memory_tool.py`:

1. **Write-Only Lock (MED-01)**: Never remove the `_write_lock` or the double-check locking pattern. Dedup queries must remain outside the lock for throughput.

2. **Tag Validation (MED-05)**: Always validate tags in `tools/memory_tool.py` before passing to `core/memory.py`. Never bypass the regex checks.

3. **Protected Pruning**: Never remove the automatic exclusion of `COLLECTION_PROCEDURAL` from `prune()`. Manual overrides via `collections=["procedural"]` are intentional.

4. **Decay Scoring**: The floor of `0.3` is critical. Never allow decay to drop memories to zero.

5. **Query Rewriting**: The `_rewrite_query()` function is model-free for speed. Do not add LLM calls here.

6. **Cancellation Guards**: All store/delete operations check `ensure_not_cancelled(trace_id)` before mutating. Never remove these guards.

7. **Thread Safety**: ChromaDB's internal locking is insufficient. Always use `self._write_lock` for inserts.

8. **Error Handling**: Dedup failures are non-fatal (store anyway). ChromaDB query failures are logged but do not crash the system.

9. **Metadata Fields**: Always populate all `META_FIELDS` when storing. Missing fields break recall filtering.

10. **Size Limits**: Respect `cfg.memory_max_entry_bytes` (default 10KB). Chunk or summarize larger content before storing.

---

## 🔮 Future Enhancements (Planned)

- **Model-based query rewriting**: Use Router model for semantic expansion (Phase 8)
- **Hierarchical indexing**: Multi-level ChromaDB indexes for very large memory stores
- **Memory consolidation**: Automatic summarization of old episodic memories into semantic
- **Procedural learning**: Auto-distill successful workflow outcomes into procedural memories
- **Cross-session continuity**: Checkpoint and restore memory state across agent restarts