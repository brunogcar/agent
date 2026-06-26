# 🧠 Memory Backend

The memory backend is a **three-collection ChromaDB vector store** with decay scoring, query rewriting, thread-safe write operations, and two learning subsystems. It provides persistent knowledge storage across **episodic** (events), **semantic** (facts), and **procedural** (skills) collections.

**Key characteristics:**
- **Three collections** — Episodic (what happened), semantic (what you know), procedural (how to do it)
- **Four-layer dedup** — Hash guard → outer vector → inner vector (inside lock) → procedural reinforcement
- **Decay scoring** — Memories fade over time; procedural memories bypass decay entirely
- **Two learning systems** — Inline meta-learning (fast) + background sleep-learning (deep)
- **Thread-safe writes** — `threading.Lock()` per collection with cancellation guards
- **Context budgeting** — Cognitive priority-based message trimming before LLM calls
- **Autonomous maintenance** — Diversity enforcer, janitor daemon, eviction engine

---

## 🏗️ Architecture

### Component Map

```
core/memory.py                          # Thin facade — re-exports singleton
core/memory_backend/
├── store.py                            # MemoryStore class: collections, _write_lock, stats
├── write_ops.py                        # execute_store() — TOCTOU-safe dedup + insert
├── read_ops.py                         # execute_recall(), execute_recall_context()
├── scoring.py                          # 4-factor confidence scoring + query rewriting
├── maintenance.py                      # execute_delete/prune/summarize/stats/diversity_maintenance()
├── telemetry.py                        # RecallTracker — RAM buffer, periodic ChromaDB flush
├── eviction.py                         # EvictionQueue class + flusher_loop() — disk spill queue
├── janitor.py                          # archive_old_episodes() — episodic archival only
├── constants.py                        # COLLECTION_PROCEDURAL, META_FIELDS, dedup thresholds
├── client.py                           # get_client(timeout=60) — ChromaDB client singleton
├── budget.py                           # Cognitive context budgeting (7-tier ContextClass:
│                                        #   SYSTEM/USER/ERROR/PROCEDURAL/RECENT/OUTPUT/ARCHIVE)
├── pruner.py                           # VRAM context pruning (artifact preservation + truncation)
├── meta_learning.py                    # distill_and_store() + MetaLearner — inline learning from traces
└── procedural/                         # distill.py, prompts.py, validate.py

core/sleep_learn/                       # Background meta-learning daemon
├── daemon.py                           # start_background_daemon() — midnight scheduler
├── feedback.py                         # Pending feedback processing loop
├── distiller.py                        # Trace analysis → rule extraction
├── filters.py                          # New rules, deduplication, contradictions
├── storage.py                          # Write rules to isolated ChromaDB collection
├── injector.py                         # Merge rules into Planner system prompt
├── logger.py                           # Parse feedback.log for pending entries
├── config.py                           # SLEEP_* configuration constants
├── sweeper.py                          # Placeholder — not yet implemented
└── janitor.py                          # Placeholder — not yet implemented
```

### Thin Facade Pattern

```python
# core/memory.py — What callers see
from core.memory_backend.store import memory  # Singleton

# Usage throughout the codebase
from core.memory import memory
memory.remember("ChromaDB uses cosine similarity", collection="semantic")
results = memory.recall("How does ChromaDB work?", top_k=5)
```

### Data Flow: Write Path

```mermaid
graph TD
    A["Caller<br/>tool / workflow / planner"] -->|"memory.remember(text, ...)"| B["write_ops.remember()"]
    B --> C["ensure_not_cancelled()<br/>Ghost mutation guard"]
    C --> D["O(1) Hash Guard<br/>store._hash_cache"]
    D -->|Exact match| E["Return skip payload<br/>status: 'skipped_duplicate'"]
    D -->|No match| F["Semantic Dedup<br/>ChromaDB query, cosine > threshold"]
    F -->|Match found| G{Collection?}
    G -->|"procedural"| H["Reinforce existing<br/>increment reinforcement_count"]
    G -->|"episodic / semantic"| E
    F -->|No match| I["Acquire _write_lock"]
    I --> J["Re-check Hash + Vector<br/>Inside lock (double-check)"]
    J -->|Match| E
    J -->|No match| K["col.add()<br/>Insert into ChromaDB"]
    K --> L["Update _hash_cache<br/>Add hash to set"]
    L --> M["Return success payload"]
```

### Data Flow: Read Path

```mermaid
graph TD
    A["Caller"] -->|"memory.recall(query, top_k)"| B["read_ops.recall()"]
    B --> C["_rewrite_query()<br/>Strip filler, expand abbreviations"]
    C --> D["Scoring.query_with_score()<br/>ChromaDB similarity search"]
    D --> E["Apply decay scoring<br/>episodic/semantic: time-decay<br/>procedural: bypass"]
    E --> F["Filter archived<br/>exclude archived=true"]
    F --> G["Sort by composite score<br/>descending"]
    G --> H["Return top_k results"]
```

---

## 🗄️ Three Collections

| Collection | Purpose | Use Cases | Dedup Threshold | Decay | Pruning |
|------------|---------|-----------|-----------------|-------|---------|
| **episodic** | What happened | Task runs, workflow outcomes, errors, evicted context | 0.85 cosine sim | Yes (30-day half-life) | Archived after 30 days |
| **semantic** | What you know | Facts, research, domain knowledge, documentation | 0.85 cosine sim | Yes (30-day half-life) | Vacuum removes low-scored |
| **procedural** | How to do it | Fix patterns, solutions, reusable approaches | 0.85 cosine sim | **No** (bypass) | Protected from pruning |

### Collection Lifecycle

```mermaid
graph LR
    subgraph "Write Path"
        A["New experience"] --> B["episodic"]
        C["Research result"] --> D["semantic"]
        E["Learned pattern"] --> F["procedural"]
    end
    subgraph "Evolution"
        B -->|"After 30 days"| G["episodic_archive"]
        B -->|"refresh_semantic()"| D
        F -->|"Diversity Enforcer"| H["Merge duplicates"]
        F -->|"Archival (90 days)"| I["Purged"]
    end
    subgraph "Read Path"
        B --> J["recall()"]
        D --> J
        F --> J
        H --> J
    end
```

---

## 🛡️ Four-Layer Deduplication

Every write passes through four dedup layers before touching ChromaDB:

### Layer Architecture

```mermaid
graph TD
    A["Incoming text"] --> B["Layer 1: Hash Guard<br/>O(1) set lookup<br/>No lock, no I/O"]
    B -->|Hit| Z["Return skip payload"]
    B -->|Miss| C["Layer 2: Outer Vector<br/>ChromaDB cosine query<br/>No lock, best-effort"]
    C -->|Hit| Z
    C -->|Miss| D["Layer 3: Inner Vector<br/>Re-query inside _write_lock<br/>Catches race conditions"]
    D -->|Hit| Z
    D -->|Miss| E["Layer 4: Procedural Reinforcement<br/>If procedural + match exists<br/>Increment reinforcement_count"]
    E -->|Reinforced| Z2["Return reinforce payload"]
    E -->|New| F["col.add()<br/>Insert + update hash cache"]
```

### Layer Details

| Layer | Lock? | Cost | Catches | Implementation |
|-------|-------|------|---------|----------------|
| **1. Hash Guard** | No | O(1) | Exact duplicates | `content_hash in store._hash_cache` |
| **2. Outer Vector** | No | ~5ms | Semantic duplicates | ChromaDB `query()` with cosine threshold |
| **3. Inner Vector** | Yes | ~5ms | Race conditions | Re-query inside `_write_lock` |
| **4. Procedural** | Yes | ~5ms | Duplicate rules | Increment `reinforcement_count` if match |

### Duplicate Response Payload

When a duplicate is found, the system returns a structured payload (not a blind skip) to prevent LLM retry loops:

```json
{
  "status": "skipped_duplicate",
  "reason": "semantic_match",
  "action": "reference_existing",
  "directive": "This knowledge is already in memory. Do not retry.",
  "matched_snippet": "First 200 chars of existing text...",
  "existing_id": "uuid",
  "retry_recommended": false
}
```

### Procedural Reinforcement

If a semantic duplicate is found in the **procedural** collection, the system does NOT skip. It:
1. Fetches the existing memory
2. Increments `reinforcement_count`
3. Updates `last_reinforced` timestamp
4. Calls `col.update()` inside the write lock

This ensures frequently-reinforced rules surface higher in recall.

---

## 📊 Scoring System

### 4-Factor Confidence Score

Every memory has a composite confidence score calculated from four factors:

```python
confidence = (
    source_trust_weight      # 0.0-1.0: Trust level of the source
    × quality_score          # 0.0-1.0: Content quality (length, coherence)
    × verification_bonus     # 0.0-1.0: Whether it was verified/reinforced
    × time_decay             # 0.0-1.0: Age-based decay (episodic/semantic only)
)
```

### Decay Formulas

```mermaid
graph LR
    subgraph "Episodic / Semantic"
        A["score = importance × max(0.3, 1 - age_days / DECAY_DAYS)"]
        B["Floor: 0.3<br/>Old memories retain 30%"]
    end
    subgraph "Procedural (No Decay)"
        C["score = importance × (1.0 + 0.15 × log(1 + min(reinforcement, 10)))"]
        D["Capped logarithmic growth<br/>Prevents monopolies"]
    end
```

| Collection | Decay? | Formula | Floor | Boost |
|------------|--------|---------|-------|-------|
| episodic | Yes | `importance × max(0.3, 1 - age/30)` | 0.3 (30%) | None |
| semantic | Yes | `importance × max(0.3, 1 - age/30)` | 0.3 (30%) | None |
| procedural | **No** | `importance × (1.0 + 0.15 × log(1 + reinforcements))` | None | Logarithmic, capped at 10 |

### Query Rewriting

Before hitting ChromaDB, queries pass through a **model-free** rewrite step in `scoring.py`:

| Transformation | Example |
|----------------|---------|
| Strip filler words | "How do I **actually** fix this?" → "fix this" |
| Expand abbreviations | "py error" → "python error" |
| Preserve question starters | "What is ChromaDB" → kept as-is |
| Lowercase normalization | "ChromaDB Query" → "chromadb query" |

> ⚠️ **No LLM calls here.** Query rewriting is deliberately model-free for speed.

---

## 🔒 Thread Safety & Concurrency

### Write-Only Lock Pattern

```mermaid
graph TD
    A["remember() called"] --> B["Hash Guard check<br/>No lock — O(1)"]
    B --> C["Outer Vector check<br/>No lock — best effort"]
    C --> D["Acquire _write_lock"]
    D --> E["Re-check Hash<br/>Inside lock"]
    E --> F["Re-check Vector<br/>Inside lock"]
    F --> G["col.add() or col.update()"]
    G --> H["Release lock"]
    H --> I["Update _hash_cache"]
```

**Key rules:**
- **Reads (`recall()`) are never locked** — ChromaDB handles concurrent reads internally
- **Writes are serialized** per collection via `threading.Lock()`
- **Double-check pattern** — Hash and vector are checked both outside and inside the lock
- **Hash cache sync** — `_hash_cache.discard()` is called on delete/prune to prevent ghost entries

### Cancellation Guards

All write operations check `ensure_not_cancelled(trace_id)` before mutating:

```python
from core.runtime.cancellation import ensure_not_cancelled

def remember(text, collection, trace_id, ...):
    ensure_not_cancelled(trace_id)  # Abort if workflow cancelled
    # ... proceed with write
```

This prevents "ghost mutations" — writes that happen after a workflow is cancelled but before the cancellation signal propagates.

---

## 🧠 Two Learning Systems

The memory backend has **two parallel systems** that extract procedural rules from execution history:

### System Comparison

```mermaid
graph TD
    subgraph "Inline Learning (meta_learning.py)"
        A["Successful tool execution"] --> B["Extract cause → effect"]
        B --> C{"Confidence > 30%?"}
        C -->|Yes| D["Write to main procedural collection"]
        C -->|No| E["Skip"]
    end
    subgraph "Background Learning (sleep_learn/)"
        F["Agent idle > 2 hours"] --> G["Process pending_feedback.log"]
        G --> H["Analyze traces for patterns"]
        H --> I{"Confidence > 60%<br/>AND repetitions > 5?"}
        I -->|Yes| J["Write to isolated procedural_meta"]
        I -->|No| K["Skip"]
    end
    D --> L["Injector merges both<br/>into Planner prompt"]
    J --> L
```

### Detailed Comparison

| Aspect | Inline (`meta_learning.py`) | Background (`sleep_learn/`) |
|--------|---------------------------|---------------------------|
| **When** | After successful tool execution | During idle periods (>2h) or midnight |
| **Threshold** | 30% confidence | 60% confidence + 5+ repetitions |
| **Collection** | Main `procedural` | Isolated `procedural_meta` |
| **Latency** | Immediate effect | Deferred (next session) |
| **Source** | Single execution context | Cross-trace pattern analysis |
| **Dedup** | Hash + vector on main collection | Hash + vector on isolated collection |

### Injection Path

Both systems converge at the **injector** (`sleep_learn/injector.py`), which merges rules from both collections into the Planner's system prompt:

```python
# Injector reads from both collections
rules_main = memory.recall("", collection="procedural", top_k=20)
rules_sleep = memory_sleep.recall("", collection="procedural_meta", top_k=20)

# Merges by hash dedup, injects into Planner prompt
prompt = base_prompt + "\n\n# Learned Rules\n" + merged_rules
```

### Feedback Loop

```
Tool execution → success/failure logged to pending_feedback.log
    → Sleep daemon processes feedback (every 10min during idle)
    → Distiller extracts rules via LLM (15s timeout)
    → Filters: new rules only, dedup, contradiction check
    → Storage: write to procedural_meta collection
    → Injector: merge into Planner prompt
    → Next execution benefits from learned rules
```

---

## 🧹 Maintenance & Cleanup

### Diversity Enforcement (Procedural Collection)

To prevent procedural memory pollution (near-duplicate or contradictory rules):

| Step | Trigger | Action |
|------|---------|--------|
| **Greedy Clustering** | Idle > 4h AND > 7 days since last run | Query top-20 neighbors, group rules with cosine distance < 0.12 |
| **Champion Selection** | Cluster with >1 rule | Highest-scoring rule becomes "Champion" |
| **Absorption** | Champion selected | `champ_score + log10(1 + sum(loser_scores))` — prevents runaway inflation |
| **Contradiction Guard** | Opposing polarity detected | Flag `contradiction_flagged: true`, don't merge |
| **Stale Archival** | `recall_count == 0` AND age > 30 days | Flag `archived: true` |
| **Permanent Purge** | `archived: true` AND age > 90 days | Delete from ChromaDB |

### Janitor Daemon

Runs during Sleep & Learn idle cycles or manually via `memory(action="janitor")`:

| Operation | Default Threshold | Action |
|-----------|-------------------|--------|
| Episodic archival | 30 days (`ARCHIVE_AGE_DAYS`) | Move to `episodic_archive` collection |
| Rule purging | 90 days (`PURGE_AGE_DAYS`) | Delete procedural rules |
| Confidence purge | score < 0.3 | Delete rules whose confidence dropped |
| ChromaDB compaction | On-demand | Force `chromadb.Client.persist()` |

### Eviction Engine

When working memory exceeds the context budget:

1. Low-priority state fields are offloaded to `episodic` collection
2. Replaced with clean placeholders in working memory
3. Offloading happens asynchronously (WAL-spill queue) to avoid blocking the hot path

### Memory Vacuum

```python
memory.memory_vacuum()
# Removes: low-scored episodic (>30 days), stale semantic (>60 days)
# Preserves: procedural (protected), critical/protected tags
```

### Protected Memories

These are immune to automatic pruning:

| Protection | Applies To | How |
|------------|-----------|-----|
| Collection | `procedural` | Never pruned by `memory.prune()` |
| Tag: `"summary"` | Any collection | Skipped during vacuum |
| Tag: `"critical"` | Any collection | Skipped during vacuum |
| Tag: `"protected"` | Any collection | Skipped during vacuum |

---

## 📐 Context Budgeting

The context budget system decides what information enters the LLM's context window during long workflows.

### Cognitive Categories

| Category | Priority | Trim Strategy | Max Chars | Examples |
|----------|----------|---------------|-----------|----------|
| `procedural` | 1 (highest) | `tail` (keep latest) | 4000 | Rules, instructions |
| `core_facts` | 2 | `smart` (scored) | 3000 | Key facts, entity summaries |
| `tool_outputs` | 3 | `tail` (keep latest) | 8000 | Tool results, web scrapes |
| `conversational` | 4 | `head` (keep earliest) | 4000 | User/assistant messages |
| `social` | 5 (lowest) | `head` (keep earliest) | 2000 | Greetings, acknowledgments |

### Budget Flow

```mermaid
graph TD
    A["All messages<br/>system + context + history"] --> B["Categorize by cognitive role"]
    B --> C["Estimate tokens<br/>len(text) // 3.5"]
    C --> D{Fits in<br/>context window?}
    D -->|Yes| E["Return as-is"]
    D -->|No| F["Trim lowest priority first"]
    F --> G["Apply per-class soft caps"]
    G --> H{Still over?}
    H -->|Yes| I["Context pruner<br/>Level 1-4 compression"]
    H -->|No| J["Return trimmed messages"]
    I --> J
```

### Compression Levels (Context Pruner)

| Level | Action | When |
|-------|--------|------|
| 1 | Truncate tool outputs to `max_chars` | Tool output > 4000 chars |
| 2 | Drop lowest-priority messages | Still over budget after L1 |
| 3 | Truncate system prompt tail | System prompt > 2000 chars |
| 4 | Hard truncation with notice | All else fails |

---

## 🔍 Tag Validation

Tags are validated in `tools/memory_tool.py` before passing to the backend:

| Rule | Validation |
|------|------------|
| Max tags per entry | 6 (`MAX_TAGS_PER_ENTRY`) |
| Max tag length | 50 chars (`MAX_TAG_LENGTH`) |
| Must start with | Letter `[a-zA-Z]` |
| Blocked characters | `< > " ' \` \|` (XSS/injection prevention) |
| Blocked patterns | Script tags, HTML entities |

---

## 📡 API Reference

### Write Operations

#### `remember()` — Store a Memory

```python
result = memory.remember(
    text="ChromaDB uses cosine similarity for vector search",
    collection="semantic",
    tags=["chromadb", "vector-search"],
    importance=0.8,
    trace_id="abc123",
)
```

| Param | Type | Default | Description |
|-------|------|---------|-------------|
| `text` | `str` | — | **Required.** Memory content |
| `collection` | `str` | `"episodic"` | Target collection |
| `tags` | `list[str]` | `[]` | Tags for filtering |
| `importance` | `float` | `0.5` | Base importance score (0.0–1.0) |
| `trace_id` | `str` | `""` | Trace identifier |
| `source` | `str` | `""` | Source attribution |
| `metadata` | `dict` | `{}` | Additional metadata |

**Returns:** `dict` — `{"status": "success", "id": "uuid"}` or `{"status": "skipped_duplicate", ...}`

#### `write_procedural_rule()` — Store a Rule

```python
result = memory.write_procedural_rule(
    rule="When ChromaDB returns empty results, check if the collection was compacted",
    source="autocode_workflow",
    confidence=0.85,
    trace_id="abc123",
)
```

### Read Operations

#### `recall()` — Query Memory

```python
results = memory.recall(
    query="How does ChromaDB deduplication work?",
    top_k=5,
    collection="semantic",
    trace_id="abc123",
)
```

| Param | Type | Default | Description |
|-------|------|---------|-------------|
| `query` | `str` | — | **Required.** Natural language query |
| `top_k` | `int` | `cfg.memory_top_k` | Max results to return |
| `collection` | `str` | `None` | Specific collection, or `None` for all |
| `trace_id` | `str` | `""` | Trace identifier |
| `min_score` | `float` | `0.0` | Minimum confidence threshold |

**Returns:** `list[dict]` — Each result has `text`, `collection`, `score`, `tags`, `metadata`, `id`

#### `memory_search()` — Search with Filters

```python
results = memory.memory_search(
    query="timeout fix",
    tags=["python", "timeout"],
    collection="procedural",
    top_k=10,
)
```

#### `semantic_search()` — Raw ChromaDB Query

```python
results = memory.semantic_search(
    query="vector database configuration",
    collection="semantic",
    top_k=5,
)
```

### Maintenance Operations

| Operation | Method | Description |
|-----------|--------|-------------|
| Deduplicate | `memory.deduplicate()` | Cross-collection deduplication |
| Forget | `memory.forget(query, collection)` | Remove specific memories |
| Vacuum | `memory.memory_vacuum()` | Remove stale/low-scored entries |
| Report | `memory.memory_report()` | Statistics and health |
| Compact | `memory.compact()` | Force ChromaDB compaction |
| Stats | `memory.stats()` | Collection counts and sizes |
| Janitor | `memory(action="janitor")` | Run maintenance daemon |

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
| `SLEEP_MIN_IDLE_SECONDS` | `7200` (2h) | Minimum idle time before background learning |
| `SLEEP_CHECK_INTERVAL` | `600` (10min) | How often to check if agent is idle |
| `SLEEP_FEEDBACK_MIN_AGE_HOURS` | `24` | Minimum age of feedback before processing |
| `SLEEP_MAX_TRACES` | `50` | Maximum traces to analyze per session |
| `SLEEP_CONFIDENCE_THRESHOLD` | `0.6` | Minimum confidence for rule extraction |
| `SLEEP_REPETITION_THRESHOLD` | `5` | Minimum repetitions before a pattern becomes a rule |
| `SLEEP_RULE_MAX_CHARS` | `1000` | Maximum characters per extracted rule |

---

## 📊 Observability

### Collection Statistics

```python
stats = memory.stats()
# Returns:
# {
#   "episodic": {"count": 1234, "size_bytes": 456789},
#   "semantic": {"count": 567, "size_bytes": 234567},
#   "procedural": {"count": 89, "size_bytes": 12345},
#   "procedural_meta": {"count": 23, "size_bytes": 5678},
# }
```

### Memory Report

```python
report = memory.memory_report()
# Returns detailed health report including:
# - Collection sizes and counts
# - Average confidence scores
# - Oldest/newest entry ages
# - Dedup hit rates
# - Archival statistics
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

## 🔀 When to Use What

| Scenario | Collection | Method |
|----------|-----------|--------|
| Store a conversation outcome | `episodic` | `memory.remember(text, collection="episodic")` |
| Store a research finding | `semantic` | `memory.remember(text, collection="semantic")` |
| Store a reusable pattern | `procedural` | `memory.write_procedural_rule(rule, ...)` |
| Search for facts | `semantic` | `memory.recall(query, collection="semantic")` |
| Search for how-to patterns | `procedural` | `memory.recall(query, collection="procedural")` |
| Search across everything | All | `memory.recall(query)` (no collection filter) |
| Remove stale entries | — | `memory.memory_vacuum()` |
| Check memory health | — | `memory.memory_report()` |
| Force cleanup | — | `memory(action="janitor")` |

---

## 🧪 Testing

```powershell
# Run all memory backend tests
D:\mcp\agent\venv\Scripts\pytest.exe tests/core/memory_backend/ -v

# Test write operations and dedup
D:\mcp\agent\venv\Scripts\pytest.exe tests/core/memory_backend/test_write_ops.py -v

# Test scoring and query rewriting
D:\mcp\agent\venv\Scripts\pytest.exe tests/core/memory_backend/test_scoring.py -v

# Test maintenance and vacuum
D:\mcp\agent\venv\Scripts\pytest.exe tests/core/memory_backend/test_maintenance.py -v

# Test context budgeting
D:\mcp\agent\venv\Scripts\pytest.exe tests/core/test_context_budget.py -v
```

**Mock strategy:**
- Mock `chromadb.Collection` for all unit tests
- Mock `cfg` for threshold and path configuration
- Use `reset_memory_state` fixture to clear globals between tests

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
4. **Incomplete implementation** — `sleep_learn/sweeper.py` and `sleep_learn/janitor.py` are placeholders. SLEEP_LEARN.md describes a 5-phase architecture but only feedback processing and distiller are operational.

**Suggestion:**
Consider consolidating into a single pipeline with two modes (fast/deep) writing to the same collection with `source` metadata. The sweeper and janitor should either be implemented or removed from docs.

### Two Context Budgeting Systems

**What exists:**
- `core/context_budget.py` — cognitive priority-based budgeting with categories and trim strategies. Uses `// 3.5` token estimation.
- `core/memory_backend/budget.py` — raw token truncation with `// 4` estimation.

**The concern:**
Two systems with different estimation factors produce inconsistent results. `context_budget.py` is the canonical system used by `LLMClient`, but `budget.py` exists separately.

**Suggestion:**
Consolidate into a single module. Make `context_budget.py` the public API, keep `budget.py` as an internal utility.

---

## 🛡️ AI Agent Instructions

If you are an AI assistant modifying the memory backend:

1. **Thin orchestrator** — never add logic to `core/memory.py` or `store.py`. Logic belongs in `write_ops.py`, `read_ops.py`, etc.
2. **Write-only lock** — never remove the `_write_lock` or the double-check locking pattern. Never lock `recall()` operations.
3. **O(1) hash guard** — never remove the `store._hash_cache` synchronization. Call `.discard()` on delete/prune.
4. **Contextual feedback** — never return a blind `{"status": "skipped_duplicate"}`. Always use the structured payload with `directive` and `matched_snippet`.
5. **Procedural reinforcement** — never skip procedural duplicates. Always increment `reinforcement_count` inside the write lock.
6. **Decay bypass** — never apply time-decay to `collection == "procedural"`.
7. **Cancellation guards** — all write operations must check `ensure_not_cancelled(trace_id)` before mutating. Never remove these guards.
8. **Tag validation** — always validate tags in `tools/memory_tool.py` before passing to the backend. Block `< > " ' \ |`.
9. **Query rewriting** — the `_rewrite_query()` function is model-free for speed. Do not add LLM calls here.
10. **Diversity enforcement** — never manually delete or merge procedural rules. The background Diversity Enforcer handles this autonomously.
11. **Protected pruning** — never prune `procedural` collection or memories tagged `"summary"`, `"critical"`, `"protected"`.

---

## 🔗 Source Code Reference

| File | Purpose |
|------|---------|
| `core/memory.py` | Thin facade — re-exports `memory` singleton |
| `core/memory_backend/store.py` | `ChromaDBMemory`: collections, stats, compact, delete |
| `core/memory_backend/write_ops.py` | `remember()`, `write_procedural_rule()`, dedup pipeline |
| `core/memory_backend/read_ops.py` | `recall()`, `memory_search()`, `semantic_search()` |
| `core/memory_backend/scoring.py` | 4-factor confidence scoring, query rewriting |
| `core/memory_backend/maintenance.py` | `deduplicate()`, `forget()`, `memory_vacuum()`, `memory_report()` |
| `core/memory_backend/telemetry.py` | Opik integration for observability |
| `core/memory_backend/eviction.py` | `EvictionEngine`: pruning, compaction, budget enforcement |
| `core/memory_backend/janitor.py` | `MaintenanceDaemon`: background memory health |
| `core/memory_backend/constants.py` | Shared constants (banned files, limits) |
| `core/memory_backend/client.py` | `get_client(timeout=60)` — ChromaDB client singleton |
| `core/memory_backend/budget.py` | Cognitive priority-based context budgeting (7-tier) |
| `core/memory_backend/pruner.py` | Overflow-aware context compression (VRAM artifact pruning) |
| `core/memory_backend/meta_learning.py` | Inline learning, heuristic/template-based |
| `core/sleep_learn/daemon.py` | Background daemon startup |
| `core/sleep_learn/feedback.py` | Pending feedback processing |
| `core/sleep_learn/distiller.py` | Trace analysis → rule extraction |
| `core/sleep_learn/filters.py` | New rules, dedup, contradictions |
| `core/sleep_learn/storage.py` | Write rules to isolated collection |
| `core/sleep_learn/injector.py` | Merge rules into Planner prompt |
| `core/sleep_learn/config.py` | SLEEP_* configuration constants |
| `core/runtime/cancellation.py` | `ensure_not_cancelled()` — ghost mutation guard |
| `core/config.py` | Memory tuning params, ChromaDB paths |

---

## 🔮 Future Roadmap

| Status | Enhancement | Description |
|--------|-------------|-------------|
| ✅ Complete | Three-collection architecture | Episodic, semantic, procedural |
| ✅ Complete | Four-layer dedup | Hash guard + outer vector + inner vector + procedural reinforcement |
| ✅ Complete | Decay scoring | Time-decay with procedural bypass |
| ✅ Complete | Context budgeting | Cognitive priority-based message trimming |
| ✅ Complete | Diversity enforcement | Autonomous procedural collection cleanup |
| ✅ Complete | Inline meta-learning | `meta_learning.py` — fast, low-threshold |
| 🚧 Partial | Background sleep-learning | Daemon works, sweeper/janitor are placeholders |
| 🚧 Planned | Consolidated learning pipeline | Merge inline + background into single system |
| 🚧 Planned | Multi-modal memory | Image and audio embeddings |
| 🚧 Planned | Memory graph | Relationship tracking between memories |
| 🚧 Planned | Cross-session learning | Share learned rules across agent instances |

---

*Last updated: June 2026. All collection names, scoring formulas, and configuration values reflect current source code.*