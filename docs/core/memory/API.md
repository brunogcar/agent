<- Back to [Memory Backend Overview](../MEMORY.md)

# 📝 API Reference

## Write Operations

### `store()` — Store a Memory

```python
result = memory.store(
    text="ChromaDB uses cosine similarity for vector search",
    memory_type="semantic",
    tags="chromadb,vector-search",
    importance=7,
    trace_id="abc123",
)
```

| Param | Type | Default | Description |
|-------|------|---------|-------------|
| `text` | `str` | — | **Required.** Memory content |
| `memory_type` | `str` | `"semantic"` | Target collection: `episodic` / `semantic` / `procedural` |
| `tags` | `str` | `""` | Comma-separated tags |
| `importance` | `int` | `5` | Base importance score (1–10) |
| `trace_id` | `str` | `""` | Trace identifier |
| `source` | `str` | `""` | Source attribution |
| `goal` | `str` | `""` | What was being attempted (episodic/procedural) |
| `outcome` | `str` | `"unknown"` | `success` / `failure` / `partial` / `unknown` |
| `tools_used` | `str` | `""` | Comma-separated tool names (episodic) |

**Typed helpers:**
- `store_episodic(text, importance=5, tags="", trace_id="", goal="", outcome="unknown", tools_used="")`
- `store_semantic(text, importance=5, tags="", trace_id="", source="")`
- `store_procedural(text, importance=7, tags="", trace_id="", goal="", outcome="success")`

**Returns:** `dict` — `{"status": "stored", "id": "uuid"}` or `{"status": "skipped_duplicate", ...}` or `{"status": "reinforced", ...}`

---

### `store_chunked()` — Store Linked Chunks (v1.1)

Stores a list of pre-split text chunks as linked memories in a single batch. All chunks share a `source_doc_id` (UUID) and carry `chunk_index` / `chunk_count` metadata.

```python
result = memory.store_chunked(
    chunks=["paragraph 1...", "paragraph 2...", "paragraph 3..."],
    memory_type="semantic",
    importance=7,
    tags="research,chunked",
    trace_id="abc123",
)
```

| Param | Type | Default | Description |
|-------|------|---------|-------------|
| `chunks` | `list[str]` | — | **Required.** Pre-split chunk texts |
| `memory_type` | `str` | `"semantic"` | Target collection. Procedural is rejected by the tool layer (reinforcement conflict). |
| `importance` | `int` | `5` | Base importance (applied to all chunks) |
| `tags` | `str` | `""` | Comma-separated tags (applied to all chunks) |
| `trace_id` | `str` | `""` | Trace identifier |
| `source` | `str` | `""` | Source attribution (URL, file path) |
| `goal` | `str` | `""` | What was being attempted |
| `outcome` | `str` | `"unknown"` | `success` / `failure` / `partial` / `unknown` |
| `tools_used` | `str` | `""` | Comma-separated tool names |

**Dedup:** Hash-only (exact match). Vector dedup is **skipped** — chunks from the same document are semantically similar and would falsely trigger the vector dedup pipeline in `execute_store()`. See `write_ops.execute_store_chunked()` for rationale.

**Returns:** `dict` — `{"status": "stored", "source_doc_id": "uuid", "stored": N, "skipped_duplicates": M, "chunk_count": N, "collection": "semantic"}`

**Recall metadata (v1.1):** `recall()` results now include `source_doc_id`, `chunk_index`, `chunk_count`. Non-chunked memories return defaults (`""`, `None`, `0`).

---

## Read Operations

### `recall()` — Query Memory

```python
results = memory.recall(
    query="How does ChromaDB deduplication work?",
    top_k=5,
    collections=["semantic"],
    trace_id="abc123",
)
```

| Param | Type | Default | Description |
|-------|------|---------|-------------|
| `query` | `str` | — | **Required.** Natural language query |
| `top_k` | `int` | `cfg.memory_top_k` | Max results to return |
| `collections` | `list[str]` | `None` | Specific collections, or `None` for all |
| `trace_id` | `str` | `""` | Trace identifier |
| `min_score` | `float` | `0.5` | Minimum confidence threshold |
| `tags_filter` | `str` | `""` | Comma-separated — only return memories with ANY of these tags |

**Returns:** `list[dict]` — Each result has `text`, `collection`, `score`, `tags`, `metadata`, `id`

### `recall_context()` — Formatted Context String

```python
context = memory.recall_context(
    query="how to fix syntax errors",
    top_k=3,
    collections=["procedural"],
)
# Returns: "[procedural | score=0.95 | 2d ago] To fix SyntaxError..."
```

---

## Maintenance Operations

| Operation | Method | Description |
|-----------|--------|-------------|
| Delete | `memory.delete(query, collections, threshold, confirm_ids)` | Remove specific memories by similarity |
| Prune | `memory.prune(max_age_days, min_importance, dry_run, collections)` | Remove stale/low-scored entries |
| Summarize | `memory.summarize(collections, top_n, store_result, trace_id)` | LLM summary of top memories |
| Stats | `memory.stats()` | Collection counts and sizes |
| Diversity | `memory.execute_diversity_maintenance(dry_run)` | Cluster and merge procedural rules |

---

## 📡 Observability

### Collection Statistics

```python
stats = memory.stats()
# Returns:
# {
#   "episodic": {"count": 1234},
#   "semantic": {"count": 567},
#   "procedural": {"count": 89},
# }
```

### Memory Report

```python
report = memory.summarize(collections=["episodic", "semantic"], top_n=30)
# Returns detailed summary including:
# - Top memories by decay score
# - Key patterns and fixes learned
# - Active goals and outcomes
```

### Telemetry (Opik Integration)

The `telemetry.py` module integrates with Opik for LLM call observability:

| Metric | Description |
|--------|-------------|
| `memory_write_latency` | Time to complete a write operation |
| `memory_read_latency` | Time to complete a recall query |
| `memory_dedup_hits` | Number of duplicates caught per collection |
| `memory_reinforcements` | Number of procedural rules reinforced |

---

## 🔍 Tag Validation

Tags are validated in `tools/memory.py` before passing to the backend:

| Rule | Validation |
|------|------------|
| Max tags per entry | 6 (`MAX_TAGS_PER_ENTRY`) |
| Max tag length | 50 chars (`MAX_TAG_LENGTH`) |
| Must start with | Letter `[a-zA-Z]` |
| Blocked characters | `< > " ' \` \|` (XSS/injection prevention) |
| Blocked patterns | Script tags, HTML entities |

---

## 🔀 When to Use What

| Scenario | Collection | Method |
|----------|-----------|--------|
| Store a conversation outcome | `episodic` | `memory.store_episodic(text, ...)` |
| Store a research finding | `semantic` | `memory.store_semantic(text, ...)` |
| Store a reusable pattern | `procedural` | `memory.store_procedural(text, ...)` |
| Search for facts | `semantic` | `memory.recall(query, collections=["semantic"])` |
| Search for how-to patterns | `procedural` | `memory.recall(query, collections=["procedural"])` |
| Search across everything | All | `memory.recall(query)` (no collection filter) |
| Remove stale entries | — | `memory.prune()` |
| Check memory health | — | `memory.stats()` |
| Force cleanup | — | `memory(action="janitor")` via tool |

---

## 📐 Unified Rule Schema (v1.2 — L3 Contract)

The keystone of the Memory + Sleep_Learn merge. Both writers conform to this shape.

```python
from core.memory_backend.rule_schema import build_unified_metadata

# meta_learning writer (sets importance)
meta = build_unified_metadata(
    text="When parsing JSON, handle JSONDecodeError",
    source="meta_learner", importance=8, tags="category:bugfix",
    goal="fix JSON parsing", outcome="success", source_trace_ids="trace_001",
)

# sleep_learn writer (sets confidence)
meta = build_unified_metadata(
    text="When parsing JSON, handle JSONDecodeError",
    source="sleep_learn", confidence=0.85, source_memory_id="mem_123",
)
```

**Fields:** `type`, `source`, `source_trace_ids`, `source_memory_id`, `importance` (1-10), `confidence` (0.0-1.0), `reinforcement_count`, `last_reinforced`, `goal`, `outcome`, `reasoning`, `tools_used`, `tags`, `created_at`, `last_accessed_at`, `recall_count`, `updated_at`, `version`, `schema_version`, `provenance_count`, `text_hash`.

**Key design (collective review):**
- `importance` + `confidence` coexist — `normalize_rule_fields()` derives one from the other
- Tag schema enforced at write time (`source:*`, `domain:*`, `category:*`, `status:*`, `evidence:*`)
- `history` NOT in ChromaDB — lives in sidecar SQLite (`rule_history` table)
- Procedural records are never chunked
- `text_hash` kept for migration dedup

---

## ⚠️ Known Concerns

> **Note:** These are MiMo's observations from source code review. They are constructive suggestions, not definitive prescriptions.

### Two Parallel Learning Systems

**What exists:**
- `core/memory_backend/meta_learning.py` — inline learning, writes to main `procedural` collection. Rewritten to a heuristic/template-based extractor (no LLM call, no single confidence threshold) — each rule template carries its own fixed confidence value (0.8–0.9) as metadata. A separate `>0.95` similarity check treats near-duplicates as reinforcement rather than new rules.
- `core/sleep_learn/` — background daemon, writes to isolated `procedural_meta` collection, `SLEEP_LEARN_MIN_CONFIDENCE` gate (default **0.8**, not 0.6).

**The concern:**
Both systems extract procedural rules from execution history. The injector merges both collections into the Planner prompt. This works, but:

1. **Semantic duplicates** — the same rule expressed differently in both collections will both be injected. Hash-based dedup catches exact matches, but not paraphrases.
2. **Authority ambiguity** — when rules conflict, there's no resolution mechanism.
3. **Maintenance burden** — two codebases, two sets of filters, two storage paths.
4. **Incomplete implementation** — The sweeper and janitor in `sleep_learn/` are partially implemented (sweeper is Phase 1 passive observation only; janitor has full purge logic). Full unification requires a dedicated testing session.

**Suggestion:**
Consider consolidating into a single pipeline with two modes (fast/deep) writing to the same collection with `source` metadata. The sweeper needs tracer/memory integration to become operational.

### Two Context Budgeting Systems

**What exists:**
- `core/llm_backend/rate_limit.py` — Rate limiting, token budgeting, and cost estimation. Uses `// 4` token estimation fallback. Handles `truncate_by_tokens()` with tiktoken and fallback.
- `core/memory_backend/budget.py` — Cognitive priority-based context budgeting with 7-tier `ContextClass` categories and trim strategies.

**The concern:**
Two systems with different estimation factors produce inconsistent results. `core/llm_backend/rate_limit.py` is the canonical system used by `LLMClient`, but `core/memory_backend/budget.py` exists separately for memory-specific context operations.

**Suggestion:**
Consolidate into a single module. Make `core/llm_backend/rate_limit.py` the public API, keep `core/memory_backend/budget.py` as an internal utility or merge it.

---

*Last updated: 2026-07-17. See [ARCHITECTURE.md](ARCHITECTURE.md) for file maps and design decisions, [CHANGELOG.md](CHANGELOG.md) for version history, [INSTRUCTIONS.md](INSTRUCTIONS.md) for AI editing rules.*
