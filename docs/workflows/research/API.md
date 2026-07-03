<- Back to [Research Overview](../RESEARCH.md)

# 📝 API Reference

## ⚡ Nodes

### `node_search(state)` — Phase 1: Web Search

**Purpose:** Search the web for relevant sources.

**Logic:**
```python
web(action="search", query=goal, max_results=3)
```

**Output:** Partial dict with `urls_data` (list of `{url, title, snippet}`).

**Error handling:** If search fails, returns `{"urls_data": []}`. The workflow proceeds with empty results.

**Note:** `max_results=3` is hardcoded despite `cfg.web_max_search_results` defaulting to 10. This is a known limitation.

---

### `node_parallel_scrape(state)` — Phase 2: Parallel Scraping

**Purpose:** Scrape multiple sources concurrently.

**Logic:**
1. Filter out already-seen URLs
2. Spawn up to 3 concurrent workers via `ThreadPoolExecutor`
3. Each worker: `web(action="read", url=...)` → LLM summarize
4. Collect results, update `seen_urls`

**Output:** Partial dict with `summaries` (list of `{url, title, summary}`).

**Error handling:**
- Individual scrape failures are logged but don't fail the workflow
- Timeout failures are caught and skipped
- LLM summarization failures are caught and skipped

**Guard:** `_is_nested_parallel()` prevents recursive parallel scraping from worker threads. Uses `threading.local()` flag.

**Note:** The `as_completed` timeout is `cfg.worker_timeout + 30` (60 + 30 = 90s). This is the timeout for the **first** future to complete, not the total time. If the first future completes quickly, subsequent futures can hang indefinitely.

---

### `route_after_search(state)` — Conditional Router

**Purpose:** Route to synthesis or END based on search results.

**Logic:**
```python
if not state.get("urls_data"):
    return "no_results"  # → END
return "has_results"     # → node_synthesize
```

**Output:** String literal `"no_results"` or `"has_results"`.

---

### `node_synthesize(state)` — Phase 3: LLM Synthesis

**Purpose:** Synthesize scraped content into a coherent answer.

**Logic:**
1. Build prompt with goal and summaries
2. Call `agent(action="dispatch", role="research", task=...)` for synthesis
3. Return the synthesized text

**Output:** Partial dict with `result` (synthesis text).

**Error handling:**
- `agent()` failure → `node_error(state, "synthesize", ...)` → workflow ends

**Critical bug:** The status check is broken:
```python
if not r.get("status") == "success":  # BUG: always False!
```
This is `(not "success") == "success"` → `False == "success"` → `False`. The error path **never fires**.

**Fix:** `if r.get("status") != "success":`

---

### `route_after_synthesize(state)` — Conditional Router

**Purpose:** Route to report or END based on synthesis result.

**Logic:**
```python
if state.get("status") == "failed":
    return "failed"  # → END
return "success"     # → node_report
```

**Output:** String literal `"failed"` or `"success"`.

---

### `node_report(state)` — Phase 4: Generate Report

**Purpose:** Generate a structured report with synthesis, sources, and metadata.

**Logic:**
1. Call `report(action="report", title=..., data=..., config=...)` with synthesis and sources
2. Return the report

**Output:** Partial dict with `report_html` and `report_path`.

**Note:** The `report` tool's `action="report"` is the report action name (generates a single-scroll HTML report), not a mistake.

---

### `node_store(state)` — Phase 5: Memory Storage

**Purpose:** Store the research result in memory.

**Logic:**
1. Store semantic memory: `memory.store_semantic(text=result[:800], ...)`

**Output:** Empty dict (side effects only).

**Note:** Only 800 chars of the result are stored in semantic memory. For long research results, this is a tiny fraction. The semantic memory will be nearly useless for recall.

---

### `node_distill(state)` — Phase 6: Distill to Procedural Memory

**Purpose:** Extract procedural knowledge from the research result.

**Logic:**
1. Call `agent(action="dispatch", role="extract", task=...)` to extract procedural knowledge
2. Store procedural memory: `memory.store_procedural(text=..., ...)`

**Output:** Empty dict (side effects only).

**Note:** The `status` check `state.get("status") == "failed"` is redundant. `node_distill` only runs on success paths.

---

### `node_notify(state)` — Phase 7: User Notification

**Purpose:** Notify the user of completion.

**Logic:**
1. Call `notify(action="notify", message=...)` with the result
2. Return `node_done(state, result=...)`

**Output:** `node_done` result dict.

**Note:** `artifacts` contains `{"sources": sources}` but `artifacts` is documented as a list of strings. This breaks consumers that expect strings.

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

*(Fill this section with relevant info from edits and refactors. Add security details as they are learned.)*

---

## 📝 Error Handling

*(Fill this section with relevant info from edits and refactors. Add error classification as it is learned.)*

---

*Last updated: 2026-07-04. See [ARCHITECTURE.md](ARCHITECTURE.md) for file maps and design decisions, [CHANGELOG.md](CHANGELOG.md) for version history, [INSTRUCTIONS.md](INSTRUCTIONS.md) for AI editing rules.*
