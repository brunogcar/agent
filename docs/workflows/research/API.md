<- Back to [Research Overview](../RESEARCH.md)

# 📝 API Reference

## ⚡ Nodes

### `node_recall(state)` — Phase 0: Recall Memories

**Purpose:** Recall relevant memories from ChromaDB for context.

**Logic:**
```python
memory.recall(query=goal, top_k=5, collections=["semantic"])
```

**Output:** Partial dict with `memory_context` (formatted string of recalled memories, or `""` if none).

---

### `node_search(state)` — Phase 1: Web Search

**Purpose:** Search the web for relevant sources.

**Logic:**
```python
# v1.0: Uses cfg.web_max_search_results (default 10) — was hardcoded to 3
web(action="search", query=goal, max_results=cfg.web_max_search_results)
```

**Output:** Partial dict with `search_results` (JSON string of `{url, title, snippet}` list, or `""` on failure).

**Error handling:** If search fails, returns `{"search_results": ""}`. The workflow proceeds — `route_after_search` checks both `search_results` and `memory_context`; if both empty, routes to END.

**v1.0 fix (#12):** URLs are deduplicated via `seen_urls` set (was only deduplicated in `parallel_scrape`).

---

### `node_parallel_scrape(state)` — Phase 2: Parallel Scraping

**Purpose:** Scrape multiple sources concurrently.

**Logic:**
1. Filter out already-seen URLs
2. Spawn up to 3 concurrent workers via `ThreadPoolExecutor`
3. Each worker: `web(action="read", url=...)` → LLM summarize
4. Collect results, update `seen_urls`
5. Build dossier string with `### [Source N]` headers
6. Hard-cap dossier at `cfg.web_max_text_chars * 2` (truncates at paragraph boundary)

**Output:** Partial dict with `search_results` (dossier string — concatenated source summaries, or `""` on failure).

**Error handling:**
- Individual scrape failures are logged but don't fail the workflow
- Timeout failures are caught and skipped
- LLM summarization failures are caught and skipped

**v1.0 fixes:**
- **#4:** Uses `concurrent.futures.wait(timeout=)` for global timeout (was `as_completed(timeout=)` — only first future)
- **#5:** Pending futures `.cancel()` on timeout — prevents zombie threads
- **#9:** `_is_nested_parallel()` guard fixed for worker thread recursion

**Guard:** `_is_nested_parallel()` prevents recursive parallel scraping from worker threads. Uses `threading.local()` flag.

---

### `route_after_search(state)` — Conditional Router

**Purpose:** Route to synthesis or END based on search results + memory context.

**Logic:**
```python
sr = state.get("search_results", "")
mc = state.get("memory_context", "")
if not sr and not mc:
    return "failed"  # → END
return "synthesize"  # → node_synthesize
```

**Output:** String literal `"failed"` or `"synthesize"`.

---

### `node_synthesize(state)` — Phase 3: LLM Synthesis

**Purpose:** Synthesize scraped content + recalled memories into a coherent answer.

**Logic:**
1. Build content block from `search_results` and `memory_context`
2. Call `agent(action="dispatch", role="research", task=...)` for synthesis
3. Return the synthesized text

**Output:** Partial dict with `result` (synthesis text).

**Error handling:**
- No source material → `node_error(state, "synthesize", "No source material to synthesize from")`
- `agent()` failure → `node_error(state, "synthesize", ...)` → workflow ends

**v1.0 fixes:**
- **#1:** Now calls `agent(action="dispatch", role="research", ...)` (was missing `action` — always returned error)
- **#2:** Status check is `r.get("status") != "success"` (was `not r.get("status") == "success"` — confusing precedence, functionally correct but hard to read)

---

### `route_after_synthesize(state)` — Conditional Router

**Purpose:** Route to trim or END based on synthesis result.

**Logic:**
```python
if state.get("status") == "failed":
    return "failed"  # → END
return "trim"        # → node_trim (v1.1)
```

**Output:** String literal `"failed"` or `"trim"`.

---

### `node_trim(state)` — Phase 3.5: Evict Oversized Search Results (v1.1 NEW)

**Purpose:** Evict oversized `search_results` to episodic memory after synthesize produces `result`.

**Logic:**
1. Calls `trim_state_node(state)` from `workflows/base.py`
2. If `search_results` exceeds ~1000 tokens (~4000 chars):
   - **Chonkie path:** Split into sentence-aware chunks → evict each individually → keep first chunk as preview
   - **Fallback path:** Whole-string eviction → generic placeholder
3. If under threshold: returns `{}` (nothing evicted, search_results passes through)

**Output:** Partial dict — `{"search_results": "<placeholder/preview>"}` if evicted, `{}` if not.

**Why this is safe:** After synthesize sets `result`, the raw `search_results` (up to 40KB) is no longer needed. `node_report`, `node_store`, `node_distill`, and `node_notify` all read `result` (not `search_results`). Evicting `search_results` reduces checkpoint bloat and enables precise recall later via `memory(recall, tags_filter="evicted")`.

---

### `node_report(state)` — Phase 4: Generate Report

**Purpose:** Generate a structured research dossier with citations.

**Logic:**
1. Get sources from `citations.get_sources(trace_id)`
2. Call `report(action="report", title=..., config=...)` with synthesis and sources
3. Return empty dict (side effect: report file generated)

**Output:** Empty dict (side effects only — report file generated).

---

### `node_store(state)` — Phase 5: Memory Storage

**Purpose:** Store the research result in semantic and episodic memory.

**Logic:**
1. Store semantic memory: `memory.store_semantic(text="Research on '{goal}':\n{result}", ...)` — **full result** (v1.0 fix #7: was `result[:800]`)
2. Store episodic memory: `memory.store_episodic(text="Completed research workflow: '{goal[:60]}'", ...)` — short summary

**Output:** Empty dict (side effects only).

**v1.0 fix (#7):** Semantic memory now stores the full `result` (was `result[:800]` — truncated, nearly useless for recall).

---

### `node_distill(state)` — Phase 6: Distill to Procedural Memory

**Purpose:** Extract procedural knowledge from the research result.

**Logic:**
1. Call `agent(action="dispatch", role="extract", task=...)` to extract procedural knowledge
2. Store procedural memory: `memory.store_procedural(text=..., ...)`

**Output:** Empty dict (side effects only).

**v1.0 fix (#8):** Removed dead `if state.get("status") == "failed": return state` check — `node_distill` only runs on success paths, so the check was dead code.

---

### `node_notify(state)` — Phase 7: User Notification

**Purpose:** Notify the user of completion.

**Logic:**
1. Call `notify(action="send", title=..., message=...)` with the result
2. Return `node_done(state, result=...)`

**Output:** `node_done` result dict.

**v1.0 fix (#10):** `artifacts` is now `list[str]` (was `list[dict]` — broke consumers expecting strings).

---

## 📤 Output

The workflow returns a `dict`:

```json
{
  "status": "success",
  "result": "ChromaDB best practices include...",
  "error": "",
  "artifacts": ["report.html"]
}
```

**Failure:**
```json
{
  "status": "failed",
  "result": "",
  "error": "Synthesis failed: timeout",
  "artifacts": []
}
```

---

## 🔒 Security

- **SSRF protection** — Web scraping goes through `core/net/` SSRF guards (URL validation, internal host blocking)
- **Citation tracking** — Sources tracked per trace_id for attribution
- **prune_tool_dict** — Final result truncated to prevent context window overflow

---

## 📝 Error Handling

| Error | Handling |
|-------|----------|
| Search fails (no results) | `route_after_search` → END (if no memory_context either) |
| Scrape timeout | Individual source skipped, others continue |
| Scrape failure | Individual source skipped, others continue |
| Synthesis failure | `node_error` → `route_after_synthesize` → END |
| No source material | `node_error("No source material to synthesize from")` → END |
| Memory store failure | Logged, non-fatal (workflow continues) |
| Notify failure | Logged, non-fatal (workflow still returns success) |

---

*Last updated: 2026-07-08. See [ARCHITECTURE.md](ARCHITECTURE.md) for file maps and design decisions, [CHANGELOG.md](CHANGELOG.md) for version history, [INSTRUCTIONS.md](INSTRUCTIONS.md) for AI editing rules.*
