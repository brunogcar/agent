<- Back to [Deep Research Overview](../DEEP_RESEARCH.md)

# 📝 API Reference

> v1.1: All nodes return **partial update dicts** (only changed keys). Citations are wired into report + notify. `WORKFLOW_METADATA` is available for MCP client introspection.

## ⚡ Nodes

### `_node_recall(state) -> dict` — Phase 1: Memory Recall

**Purpose:** Recall relevant past research from memory.

**Logic:**
```python
results = memory.recall(query=goal, top_k=5, trace_id=tid)
```

**Output:** `{"memory_context": ctx}` (partial dict).

**Error handling:** [v1.1/P1 #8] `memory.recall` is wrapped in `try/except` + `tracer.error`. On failure, returns `{"memory_context": ""}` — the workflow proceeds without context. Non-fatal.

---

### `node_decompose_goal(state) -> dict` — Phase 2: Goal Decomposition

**Purpose:** Break the goal into 3-5 sub-queries for search.

**Logic:**
1. Build prompt with goal, memory context, and current findings
2. Call `llm.complete(role="planner", ...)` for decomposition
3. Parse sub-queries from JSON or bullet list

**Output:** Partial dict with `sub_queries`, `pending_queries`.

**Error handling:**
- LLM failure → returns `{"sub_queries": [goal], "pending_queries": [goal]}` (fallback to single query)
- Parse failure → same fallback

---

### `node_search(state) -> dict` — Phase 3: Multi-Tool Search

**Purpose:** Execute pending sub-queries via Tavily → web → browser fallback; extract evidence.

**Logic:**
1. For each sub-query:
   - Select tool: Tavily (if budget + key available) → web → browser fallback
   - **[v1.1/P0 #4]** Decrement API budget on Tavily ATTEMPT (paid API charges per call regardless of outcome)
   - Execute search; on Tavily failure/empty, fall back to web
   - Extract evidence (top 3 results per query), dedup via `seen_urls` set
   - Summarize evidence via `llm.complete(role="summarize")`
   - Register sources via `citations.add(trace_id, url, title, snippet)`
2. Track consecutive empty iterations for stuck-loop detection

**Output:** Partial dict with `extracted_evidence`, `seen_urls`, `budget_api_calls`, `budget_browser_actions`, `budget_events`, `iteration`, `consecutive_empty_iterations`.

**Error handling:** Individual search failures are logged via `log_event()` but don't fail the workflow. Browser fallback failures are logged but don't fail the workflow.

**Budget rules (v1.1):**
- Tavily: decrements `budget_api_calls` on ATTEMPT (success or failure)
- Web (SearXNG): free, never decrements
- Browser: decrements `budget_browser_actions` per navigate + per text_content

---

### `node_synthesize(state) -> dict` — Phase 4: Synthesis + Evaluation

**Purpose:** Synthesize evidence into knowledge, evaluate completeness, check convergence.

**Logic:**
1. Build user prompt with goal, evidence, and previous knowledge
2. Call `agent(action="dispatch", role="research", task=user_prompt, context=SYNTHESIZE_SYSTEM_PROMPT)` for synthesis
3. Merge with previous knowledge (REPLACE semantics)
4. Call `agent(action="dispatch", role="executor", task=evaluate_prompt, context=EVALUATE_SYSTEM_PROMPT)` for evaluation
5. Parse score (0-100), check convergence via `SequenceMatcher`

**Output:** Partial dict with `knowledge_base`, `_prev_knowledge`, `completeness`, `extracted_evidence` (cleared), `converged`, `synthesis`.

**[v1.1/P0 #2] Parameter mapping (was swapped):**
- `task=` holds the user instruction (goal + evidence / goal + synthesis) → flows to `llm.complete(user=task)`
- `context=` holds the system framing prompt (`SYNTHESIZE_SYSTEM_PROMPT` / `EVALUATE_SYSTEM_PROMPT`)
- Previously `task=` held the system prompt and `content=` held the user instruction — backwards. The system prompt text landed in the `user=` slot, and the role's configured system prompt overrode the intended framing.

**[v1.1/P1 #6] Removed wrappers:** `_agent_ok` / `_agent_text` were defensive wrappers for a legacy `LLMResponse` shape. `agent()` returns a `dict` with `status`/`text` keys; the wrappers are dead code and have been removed. Nodes now check `result.get("status") == "success"` directly.

---

### `route_after_synthesize(state) -> str` — Conditional Router

**Purpose:** Decide whether to loop back to decompose or exit to report.

**Exit conditions (in order):**
1. Hard cap: `iteration >= max_iterations` → `"report"`
2. Stuck-loop: `consecutive_empty_iterations >= 2` → `"report"`
3. Dual-gate: `completeness >= threshold AND converged` → `"report"`
4. Otherwise → `"decompose"` (continue loop)

**Output:** String literal `"report"` or `"decompose"`.

---

### `_node_report(state) -> dict` — Phase 5: Report Generation

**Purpose:** Build the final report from synthesis + knowledge base, append sources.

**Logic:**
1. `report = synthesis or knowledge_base`
2. **[v1.1]** Append `## Sources` section from `citations.get_sources(trace_id)` (if any)
3. Determine status: `"success"` if `completeness >= threshold`, else `"incomplete"`

**Output:** Partial dict with `report`, `result`, `status`.

**[v1.1] Citations:** Sources collected by `node_search` via `citations.add()` are now surfaced in the report as a numbered `## Sources` section. Previously they were collected and discarded.

---

### `_node_notify(state) -> dict` — Phase 6: User Notification

**Purpose:** Notify the user of completion; surface source URLs as artifacts.

**Logic:**
1. `notify(action="send", title="DeepResearch", message=result[:500])`
2. **[v1.1]** Return `artifacts` = source URLs from `citations.get_sources(trace_id)`

**Output:** Partial dict with `artifacts` (list[str] of source URLs).

**Error handling:** [v1.1] `notify()` wrapped in `try/except` + `tracer.error`. A notification failure does not prevent `artifacts` from being returned.

---

### `_node_store(state) -> dict` — Phase 7: Memory Storage

**Purpose:** Store the research result in semantic + episodic memory.

**Logic:**
1. `memory.store_semantic(text="Deep Research: " + result, ...)` — **[v1.1/P1 #10] full result, no truncation**
2. `memory.store_episodic(text="Completed deep research workflow: ...", ...)`

**Output:** `{}` (side effects only).

**Error handling:** [v1.1] Both `store_*` calls wrapped in `try/except` + `tracer.error`. Non-fatal.

---

### `_node_distill(state) -> dict` — Phase 8: Distillation

**Purpose:** Placeholder for `sleep_learn.distill_workflow` integration.

**Output:** `{}` (no-op). Returns an empty partial dict — LangGraph merges it with no effect.

---

## 📤 Output

The workflow returns a `dict`:

```json
{
  "status": "success",
  "result": "Quantum computing error correction has seen...\n\n## Sources\n[1] Source A — https://...\n[2] Source B — https://...",
  "error": "",
  "artifacts": ["https://source-a.example", "https://source-b.example"]
}
```

**Incomplete (hard cap or stuck loop reached before convergence):**
```json
{
  "status": "incomplete",
  "result": "Partial research...",
  "artifacts": ["https://source-a.example"]
}
```

---

## 📝 Error Handling

| Failure | Node | Behavior |
|---------|------|----------|
| Memory recall fails | `_node_recall` | `tracer.error`; returns empty context (non-fatal) |
| Decompose LLM fails | `node_decompose_goal` | Falls back to `[goal]` as single sub-query |
| Tavily search fails | `node_search` | Falls back to web; Tavily budget already decremented on attempt |
| Web search fails | `node_search` | Logged; no evidence extracted for that query |
| Browser fallback fails | `node_search` | Logged; raw text used if any |
| Synthesis agent fails | `node_synthesize` | Falls back to `prev_knowledge`; score = 0 |
| Evaluate agent fails | `node_synthesize` | Score = 0; `converged = False` |
| Memory store fails | `_node_store` | `tracer.error`; returns `{}` (non-fatal) |
| Notify fails | `_node_notify` | `tracer.error`; still returns `artifacts` |

---

*Last updated: 2026-07-14 (v1.1.1). See [ARCHITECTURE.md](ARCHITECTURE.md) for file maps and design decisions, [CHANGELOG.md](CHANGELOG.md) for version history.*
