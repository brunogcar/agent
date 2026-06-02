# 🧠 Memory & Cognitive Architecture

The memory system is a three-collection ChromaDB vector store with decay scoring, query rewriting, and thread-safe write operations. It provides persistent knowledge storage across **episodic** (events), **semantic** (facts), and **procedural** (skills) collections. 

Following Phase 5 and Phase 6, the system now also features **Dynamic Cognitive Context Budgeting**, **Async Episodic Eviction**, and autonomous **Memory Diversity Enforcement**.

---

## 🏗️ Architecture Overview

### The Thin Orchestrator Pattern
Following the structural refactor, the memory system uses a Facade + Thin Orchestrator + Pure Functions pattern to ensure testability, domain isolation, and prevent state corruption.

*   **`core/memory.py` (The Facade):** A 5-line file that simply imports and exposes the `memory` singleton.
*   **`core/memory_backend/store.py` (The Orchestrator):** Holds the Singleton state (`self._client`, `self._write_lock`, `self._hash_cache`) and 1-line delegator methods.
*   **`core/memory_backend/*.py` (Pure Functions):** Stateless logic in `write_ops.py`, `read_ops.py`, `maintenance.py`, `scoring.py`, and `telemetry.py` that receives the `store` instance explicitly.

### The Cognitive Subsystems
*   **`core/memory_backend/budget.py`:** Dynamic Context Budgeting. Categorizes messages by `ContextClass` and enforces token limits before LLM calls.
*   **`core/memory_backend/eviction.py`:** Async WAL-spill queue. Offloads evicted working memory to episodic storage in the background without blocking the LangGraph hot path.
*   **`core/memory_backend/procedural/`:** The "Sleep & Learn" distillation pipeline that extracts reusable rules from successful workflows.

---

## 🗄️ Three Collections

| Collection   | Purpose           | Use Cases                                            | Default Dedup Threshold |
|--------------|-------------------|------------------------------------------------------|-------------------------|
| **episodic**   | What happened     | Task runs, workflow outcomes, errors, evicted context| 0.05 (near-identical)   |
| **semantic**   | What you know     | Facts, research, domain knowledge, documentation     | 0.15 (similar facts)    |
| **procedural** | How to do it      | Fix patterns, solutions, reusable approaches          | 0.08 (similar patterns) |

*Note: The `procedural` collection is autonomously maintained by the Diversity Enforcer. Stale rules are flagged with `archived: true` and filtered out of active recall.*

---

## 🧹 Memory Diversity Enforcement (Autonomous Maintenance)
To prevent procedural memory pollution (accumulation of near-duplicate or contradictory rules), a background daemon runs periodically to clean the `procedural` collection.

1.  **The Trigger:** Runs when the agent has been idle for > 4 hours AND > 7 days have passed since the last run. Uses `try_acquire_background_slot()` to prevent VRAM contention.
2.  **Greedy Clustering:** Walks the ChromaDB index, querying top-20 neighbors. Groups rules with a cosine distance `< 0.12`.
3.  **Champion Selection & Absorption:** Selects the highest-scoring rule as the "Champion". Absorbs the losers' reinforcement counts using a logarithmic scale (`champ + log10(1 + sum(losers))`) to prevent runaway score inflation.
4.  **Contradiction Guard:** Prevents merging rules with opposing polarity by scanning for negation words (`never`, `don't`, `avoid`, `is not`) and ensuring both rules share the same `outcome` metadata. Ambiguous clusters are flagged (`contradiction_flagged: true`) rather than force-merged.
5.  **Stale Archival:** Rules with `recall_count == 0` older than 30 days are flagged `archived: true`. After 90 days, they are permanently purged.

---

## 🧠 Dynamic Cognitive Context Budgeting
To prevent the LLM from drowning in accumulated context during long workflows, the system actively manages the flow of information into the context window.

1.  **Context Classes:** Every message is classified into a priority tier: `SYSTEM`, `USER`, `ERROR`, `PROCEDURAL`, `OUTPUT`.
2.  **Prompt Assembly:** `budget_messages()` calculates estimated tokens (`len(text) // 4`). It greedily selects the highest-scoring messages that fit the budget, enforcing per-class soft caps to prevent a single massive traceback from starving the context.
3.  **Episodic Offloading:** When working memory exceeds the budget, low-priority state fields are offloaded to the `episodic` collection via the Async WAL-spill (`eviction_queue.py`), and replaced with a clean placeholder.

---

## ⏳ Decay Scoring & Procedural Bypass

Memories fade naturally over time to prevent context pollution. Procedural memories bypass time-decay entirely.

**Formula:**
```python
# For episodic/semantic:
score = importance × max(0.3, 1 - age_days / DECAY_DAYS)

# For procedural (Time-Decay Bypass):
score = importance × (1.0 + 0.15 * math.log(1 + min(reinforcement_count, 10)))
```
*   **Floor:** `0.3` (old episodic/semantic memories retain 30% of importance).
*   **Procedural Boost:** Capped logarithmic growth prevents memory monopolies while surfacing proven rules.
*   **Archival Filter:** `read_ops.py` automatically excludes memories where `archived == true`.

---

## 🔒 Concurrency & The O(1) Hash Guard

### Write-Only Lock Pattern (MED-01)
ChromaDB's internal locking is insufficient for concurrent multi-collection writes. We use a Write-Only Lock pattern:
1.  **Outer Check (No Lock):** O(1) Hash Guard checks `store._hash_cache` (Python `set()`).
2.  **Outer Vector Check (No Lock):** Best-effort semantic dedup.
3.  **Critical Section (Locked):** `with store._write_lock:` re-checks Hash and Vector, then performs the `col.add()` or `col.update()`.

### Contextual Feedback Trap Fix
When a duplicate is found, the system NO LONGER returns a blind skip. It returns a structured payload to stop LLM retry loops:
```json
{
  "status": "skipped_duplicate",
  "reason": "semantic_match",
  "action": "reference_existing",
  "directive": "This knowledge is already in memory. Do not retry with overlapping chunks.",
  "matched_snippet": "First 200 chars of existing text...",
  "existing_id": "uuid",
  "retry_recommended": false
}
```

### Procedural Reinforcement
If a semantic duplicate is found in the `procedural` collection, the system does not skip it. It fetches the existing memory, increments `reinforcement_count`, updates `last_reinforced`, and calls `col.update()` inside the write lock to prevent race conditions.

---

## 🧠 Procedural Distillation Pipeline
Located in `core/memory_backend/procedural/`, this subsystem automatically extracts reusable rules from successful workflows.
*   **`prompts.py`:** Strict JSON schema requiring `{"has_insight": bool, "rule": "When X, do Y because Z"}`.
*   **`validate.py`:** Regex/quality filters that blacklist generic advice (e.g., "write clean code", "always test").
*   **`distill.py`:** The pipeline. Calls the Planner LLM with a hard 15-second HTTP timeout (via `httpx`) to sever the socket and free VRAM if the model stalls.
*   *Wired as a synchronous LangGraph node (`node_distill_memory`) at the end of `autocode` and `research` workflows.*

---

## 🏷️ Tag Validation, Query Rewriting & Protected Pruning

*   **Tag Validation (MED-05):** Prevents injection/XSS attacks in `tools/memory_tool.py`. Rejects dangerous chars (`< > " ' \` |`). Max 6 tags per entry, max 50 chars per tag. Must start with letter.
*   **Query Rewriting:** Lightweight, model-free transformation in `scoring.py` before hitting ChromaDB. Strips filler words, expands abbreviations (`py` -> `python`), preserves question starters.
*   **Protected Pruning:** The `procedural` collection is protected from automatic pruning (`memory.prune()`) to preserve high-value "how-to" patterns. Memories tagged `"summary"`, `"critical"`, or `"protected"` are also immune.

---

## ⚠️ AI Agent Instructions for Memory & Cognition Operations

If you are an AI assistant modifying the memory or cognition systems, you **MUST** adhere to these constraints:

1.  **Thin Orchestrator:** Never add logic to `core/memory.py` or `store.py`. Logic belongs in `write_ops.py`, `read_ops.py`, etc.
2.  **Write-Only Lock (MED-01):** Never remove the `_write_lock` or the double-check locking pattern. Never lock `recall()` operations.
3.  **O(1) Hash Guard:** Never remove the `store._hash_cache` synchronization (`.discard()` on delete/prune).
4.  **Contextual Feedback:** Never return a blind `{"status": "skipped_duplicate"}`. Always use `_build_duplicate_payload()`.
5.  **Procedural Reinforcement:** Never skip procedural duplicates. Always increment `reinforcement_count` inside the write lock.
6.  **Decay Bypass:** Never apply time-decay to `collection == "procedural"`.
7.  **VRAM Safety:** Never increase the 15s timeout in `distill.py` without understanding the `httpx` socket severing mechanics. Never use `ThreadPoolExecutor` for LLM timeouts.
8.  **Tag Validation (MED-05):** Always validate tags in `tools/memory_tool.py` before passing to the backend.
9.  **Query Rewriting:** The `_rewrite_query()` function is model-free for speed. Do not add LLM calls here.
10. **Cancellation Guards:** All store/delete operations check `ensure_not_cancelled(trace_id)` before mutating. Never remove these guards.
11. **Context Budgeting:** Never bypass `budget_messages()` in `core/llm.py`. It is the final safety net preventing VRAM OOM crashes.
12. **Diversity Enforcement:** Never manually delete or merge procedural rules. The background Diversity Enforcer handles clustering, contradiction guarding, and archival autonomously. 

### 🧹 The Janitor & Autonomous Compaction
To prevent ChromaDB bloat and keep retrieval latency low, the system includes a unified Janitor.
- **Trigger:** Runs automatically during the Sleep & Learn daemon's idle cycles, or manually via `memory(action="janitor")`.
- **Episodic Archival:** Moves episodic memories older than `ARCHIVE_AGE_DAYS` (default 30) to the `episodic_archive` collection.
- **Rule Purging:** Deletes learned procedural rules older than `PURGE_AGE_DAYS` (default 90) or rules whose confidence score drops below 0.3 due to the feedback loop.
- **Zero Startup Cost:** The janitor uses lazy `chromadb` imports, ensuring the MCP server startup time remains unaffected.
