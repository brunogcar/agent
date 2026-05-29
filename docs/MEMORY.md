
# 🧠 Memory System Architecture

The memory system is a three-collection ChromaDB vector store with decay scoring, query rewriting, and thread-safe write operations. It provides persistent knowledge storage across **episodic** (events), **semantic** (facts), and **procedural** (skills) collections.

## 🏗️ Architecture Overview

### The Thin Orchestrator Pattern
Following the Phase 1-6 refactor, the memory system uses a **Facade + Thin Orchestrator + Pure Functions** pattern to ensure testability and prevent state corruption.

- **`core/memory.py` (The Facade):** A 5-line file that simply imports and exposes the `memory` singleton.
- **`core/memory_backend/store.py` (The Orchestrator):** Holds the Singleton state (`self._client`, `self._write_lock`, `self._hash_cache`) and 1-line delegator methods.
- **`core/memory_backend/*.py` (Pure Functions):** Stateless logic in `write_ops.py`, `read_ops.py`, `maintenance.py`, and `scoring.py` that receives the `store` instance explicitly.

### Three Collections
| Collection | Purpose | Use Cases | Default Dedup Threshold |
|---|---|---|---|
| `episodic` | What happened | Task runs, workflow outcomes, errors, events | 0.05 (near-identical only) |
| `semantic` | What you know | Facts, research, domain knowledge, documentation | 0.15 (similar facts) |
| `procedural` | How to do it | Fix patterns, solutions, reusable approaches | 0.08 (similar patterns) |

### Memory Entry Schema
Every memory entry stores structured metadata in ChromaDB:
```json
{
  "text":       "str",
  "type":       "str (episodic | semantic | procedural)",
  "importance": "int (1-10)",
  "tags":       "str (comma-separated)",
  "timestamp":  "int (unix epoch)",
  "trace_id":   "str",
  "goal":       "str",
  "outcome":    "str (success | failure | partial | unknown)",
  "tools_used": "str",
  "source":     "str",
  "text_hash":  "str (SHA256 for O(1) dedup)",
  "reinforcement_count": "int (for procedural boosting)",
  "last_reinforced": "int (unix epoch)"
}
```

## ⏳ Decay Scoring & Procedural Bypass

Memories fade naturally over time to prevent context pollution. **Procedural memories bypass time-decay entirely.**

### Formula
```python
# For episodic/semantic:
score = importance × max(0.3, 1 - age_days / DECAY_DAYS)

# For procedural (Time-Decay Bypass):
score = importance × (1.0 + 0.15 * math.log(1 + min(reinforcement_count, 10)))
```
- **Floor:** `0.3` (old episodic/semantic memories retain 30% of importance).
- **Procedural Boost:** Capped logarithmic growth prevents memory monopolies while surfacing proven rules.

## 🔒 Concurrency & The O(1) Hash Guard

### Write-Only Lock Pattern (MED-01)
ChromaDB's internal locking is insufficient for concurrent multi-collection writes. We use a Write-Only Lock pattern:
1. **Outer Check (No Lock):** O(1) Hash Guard checks `store._hash_cache` (Python `set()`).
2. **Outer Vector Check (No Lock):** Best-effort semantic dedup.
3. **Critical Section (Locked):** `with store._write_lock:` re-checks Hash and Vector, then performs the `col.add()` or `col.update()`.

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
If a semantic duplicate is found in the `procedural` collection, the system does not skip it. It fetches the existing memory, increments `reinforcement_count`, updates `last_reinforced`, and calls `col.update()` **inside the write lock** to prevent race conditions.

## 🧠 Procedural Distillation Pipeline

Located in `core/memory_backend/procedural/`, this subsystem automatically extracts reusable rules from successful workflows.

1. **`prompts.py`:** Strict JSON schema requiring `{"has_insight": bool, "rule": "When X, do Y because Z"}`.
2. **`validate.py`:** Regex/quality filters that blacklist generic advice (e.g., "write clean code", "always test").
3. **`distill.py`:** The pipeline. Calls the Planner LLM with a hard **15-second HTTP timeout** (via `httpx`) to sever the socket and free VRAM if the model stalls.

Wired as a synchronous LangGraph node (`node_distill_memory`) at the end of `autocode` and `research` workflows.

## 🏷️ Tag Validation (MED-05)
Tag validation prevents injection/XSS attacks. Enforced in `tools/memory_tool.py`:
- Rejects dangerous chars: `< > " ' \` |`
- Max 6 tags per entry, max 50 chars per tag.
- Must start with letter. Allowed: alphanumeric, hyphens, dots, spaces.

## 🔍 Query Rewriting
Lightweight, model-free transformation in `scoring.py` before hitting ChromaDB:
- Strips filler words (`please`, `the`, `in`).
- Expands abbreviations (`py` -> `python`, `cfg` -> `config`).
- Preserves question starters (`how`, `what`).

## 🛡️ Protected Pruning
The `procedural` collection is protected from automatic pruning (`memory.prune()`) to preserve high-value "how-to" patterns. It can only be pruned if explicitly targeted via `collections=["procedural"]`. Memories tagged `"summary"`, `"critical"`, or `"protected"` are also immune.

## ⚠️ AI Agent Instructions for Memory Operations

If you are an AI assistant modifying the memory system, you MUST adhere to these constraints:

1. **Thin Orchestrator:** Never add logic to `core/memory.py` or `store.py`. Logic belongs in `write_ops.py`, `read_ops.py`, etc.
2. **Write-Only Lock (MED-01):** Never remove the `_write_lock` or the double-check locking pattern. Never lock `recall()` operations.
3. **O(1) Hash Guard:** Never remove the `store._hash_cache` synchronization (`.discard()` on delete/prune).
4. **Contextual Feedback:** Never return a blind `{"status": "skipped_duplicate"}`. Always use `_build_duplicate_payload()`.
5. **Procedural Reinforcement:** Never skip procedural duplicates. Always increment `reinforcement_count` inside the write lock.
6. **Decay Bypass:** Never apply time-decay to `collection == "procedural"`.
7. **VRAM Safety:** Never increase the 15s timeout in `distill.py` without understanding the `httpx` socket severing mechanics. Never use `ThreadPoolExecutor` for LLM timeouts.
8. **Tag Validation (MED-05):** Always validate tags in `tools/memory_tool.py` before passing to the backend.
9. **Query Rewriting:** The `_rewrite_query()` function is model-free for speed. Do not add LLM calls here.
10. **Cancellation Guards:** All store/delete operations check `ensure_not_cancelled(trace_id)` before mutating. Never remove these guards.