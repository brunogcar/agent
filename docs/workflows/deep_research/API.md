<- Back to [Deep Research Overview](../DEEP_RESEARCH.md)

# 📝 API Reference

## ⚡ Nodes

### `_node_recall(state)` — Phase 1: Memory Recall

**Purpose:** Recall relevant past research from memory.

**Logic:**
```python
memory.recall(
    query=goal,
    limit=5,
    trace_id=state["trace_id"],
)
```

**Output:** Partial dict with `memory_context`.

**Error handling:** If memory recall fails, returns `{"memory_context": ""}`. The workflow proceeds without context.

---

### `_node_decompose(state)` — Phase 2: Goal Decomposition

**Purpose:** Break the goal into sub-queries for parallel search.

**Logic:**
1. Build prompt with goal, memory context, and current findings
2. Call `llm.complete(role="planner", ...)` for decomposition
3. Parse sub-queries from JSON or bullet list

**Output:** Partial dict with `queries` (list of sub-query strings).

**Error handling:**
- LLM failure → returns `{"queries": [goal]}` (fallback to single query)
- Parse failure → returns `{"queries": [goal]}` (fallback to single query)

**Note:** The `_parse_sub_queries` regex has a fragile character class: `r'[\-*•]'`. The `\` escape before `*` is unnecessary and may emit a `SyntaxWarning`.

**Note:** JSON parsing doesn't handle trailing commas. LLMs sometimes output `["query1", "query2",]` which `json.loads` rejects.

---

### `_node_search(state)` — Phase 3: Multi-Tool Search

**Purpose:** Search for information using multiple tools.

**Logic:**
1. For each sub-query:
   - Select tool: Tavily API (if budget allows) → web search → browser fallback
   - Execute search
   - Extract evidence (top 3 results per query)
   - Summarize evidence
2. Update budget tracking

**Output:** Partial dict with `extracted_evidence`, `seen_urls`, `budget_api_calls`, `budget_browser_actions`.

**Error handling:**
- Individual search failures are logged but don't fail the workflow
- Budget exhaustion stops the search loop
- Browser fallback failures are logged but don't fail the workflow

**Critical bug:** API budget is decremented for ALL successful searches, including web searches (which don't consume Tavily API calls). Only Tavily searches should decrement the API budget.

**Critical bug:** API budget is NOT decremented for failed Tavily searches. The API call was made (and consumed) but the budget doesn't reflect it.

**Note:** `max_results=5` is hardcoded for search queries. Not configurable.

**Note:** `_is_js_wall` uses hardcoded indicators instead of `JS_HEAVY_HINTS` from `constants.py`. Dead code.

---

### `_node_synthesize(state)` — Phase 4: Synthesis + Evaluation

**Purpose:** Synthesize evidence and evaluate completeness.

**Logic:**
1. Build prompt with goal, evidence, and previous knowledge
2. Call `agent(action="dispatch", role="research", ...)` for synthesis
3. Parse synthesis and score from JSON
4. Call `agent(action="dispatch", role="executor", ...)` for evaluation
5. Parse evaluation score
6. Determine convergence

**Output:** Partial dict with `knowledge_base`, `_prev_knowledge`, `completeness`, `extracted_evidence`, `converged`, `synthesis`.

**Critical bug:** `agent()` calls are missing `action="dispatch"`. The `agent()` facade requires `action`.

**Critical bug:** `_agent_ok` and `_agent_text` are defensive wrappers for `LLMResponse` objects, but `agent()` returns `dict`. These wrappers are dead code.

**Critical bug:** `task` parameter is used for the system prompt, not the user task. The `agent()` facade passes `task` to `llm.complete(user=task)`. But here `SYNTHESIZE_SYSTEM_PROMPT` is passed as the user message, and the role's system prompt is ignored. This is semantically wrong.

**Bug:** `completeness_threshold` default is `0.85` in code but `85.0` in `.env`. The node and route use different scales. The `_parse_score` returns 0-100, but `completeness_threshold` from state defaults to `0.85` (from node fallback). The route checks `completeness >= threshold` which is always true for any score >= 1.

**Bug:** `_parse_score` removes negative numbers with `re.sub(r"-\d+", "", text)`. This removes ALL negative numbers, including legitimate ones in ranges like "score: 85-90" which becomes "score: 90".

---

### `route_after_synthesize(state)` — Conditional Router

**Purpose:** Route to report, search, or END based on synthesis result.

**Logic:**
```python
converged = _is_converged(prev_knowledge, knowledge_base, CONVERGENCE_SIMILARITY_THRESHOLD)
if converged:
    return "converged"  # → _node_report
if is_budget_exhausted(state):
    return "budget_exhausted"  # → _node_report
return "continue"  # → _node_search
```

**Output:** String literal `"converged"`, `"budget_exhausted"`, or `"continue"`.

**Note:** `converged` is recomputed in the route, not taken from state. The `synthesize` node already computes it. This is redundant and could diverge if the threshold changes.

---

### `_node_report(state)` — Phase 5: Report Generation

**Purpose:** Generate a structured report with the final synthesis.

**Logic:**
1. Call `report(action="report", title=..., data=..., config=...)` with synthesis and sources
2. Return the report

**Output:** Partial dict with `report_html` and `report_path`.

**Note:** If both `knowledge_base` and `synthesis` are empty, `report` is `""` and `status` is `"incomplete"`. The user gets an empty report with `"incomplete"` status — confusing.

---

### `_node_store(state)` — Phase 6: Memory Storage

**Purpose:** Store the research result in memory.

**Logic:**
1. Store semantic memory: `memory.store_semantic(text=result[:800], ...)`

**Output:** Empty dict (side effects only).

**Note:** Only 800 chars of the result are stored in semantic memory. For long research results, this is a tiny fraction.

---

### `_node_distill(state)` — Phase 7: Distillation

**Purpose:** Extract procedural knowledge from the research result.

**Logic:**
Placeholder — returns state unchanged. Not wired in v1.

**Output:** State dict (unchanged).

---

### `_node_notify(state)` — Phase 8: User Notification

**Purpose:** Notify the user of completion.

**Logic:**
1. Call `notify(action="notify", message=...)` with the result
2. Return `node_done(state, result=...)`

**Output:** `node_done` result dict.

---

## 📤 Output

The workflow returns a `dict`:

```json
{
  "status": "success",
  "result": "Quantum computing error correction has seen...",
  "error": "",
  "artifacts": ["report.html"]
}
```

**Incomplete (budget exhausted):**
```json
{
  "status": "incomplete",
  "result": "Partial research: Quantum computing error correction...",
  "error": "",
  "artifacts": ["report.html"]
}
```

**Failure:**
```json
{
  "status": "failed",
  "result": "",
  "error": "Deep research failed: timeout",
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
