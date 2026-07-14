<- Back to [Deep Research Overview](../DEEP_RESEARCH.md)

# 🛡️ AI Instructions

## ❌ NEVER DO

1. **Never mutate state in-place** — Always return partial update `dict`s.
2. **Never spread `**state`** — Never return `{**state, "key": "value"}`. Return only the changed keys.
3. **Never remove budget management** — Budget tracking prevents runaway costs.
4. **Never remove convergence detection** — Without it, the workflow would run indefinitely.
5. **Never use `print()` to stdout** — MCP stdio corruption. Use `tracer.step()` / `tracer.error()` for logging.
6. **Never create `.bak` files** — forbidden by project rules.
7. **Never rewrite the entire file** — surgical edits only. Preserve existing code exactly.
8. **Never call `agent()` without `action="dispatch"`** — The `agent()` facade requires `action`.
9. **Never use `task=` for system prompts** — `task` flows to `llm.complete(user=task)`. Use `context=` for the system framing prompt. [v1.1/P0 #2]
10. **Never use `content=` for text in synthesis/evaluate** — `content` is for base64 images. Use `context=` for system prompt, `task=` for user instruction. [v1.1/P0 #2]
11. **Never return `None` from LangGraph nodes** — Always return a `dict` (even empty `{}`).
12. **Never decrement API budget for web searches** — Only Tavily (paid) decrements `budget_api_calls`. Web (SearXNG) and browser are free. [v1.0.2]
13. **Never decrement API budget only on Tavily success** — Tavily charges per call attempt. Decrement on ATTEMPT, not success. [v1.1/P0 #4]
14. **Never truncate `result` before storing in semantic memory** — Semantic memory is for content retrieval; truncation defeats the purpose. Store the full result. [v1.1/P1 #10]
15. **Never silently swallow memory/notify failures** — Wrap in `try/except` + `tracer.error`. Non-fatal, but must be logged. [v1.1/P1 #8]
16. **Never re-add `_agent_ok` / `_agent_text` wrappers** — `agent()` returns a `dict`; check `result.get("status") == "success"` directly. [v1.1/P1 #6]

## ✅ ALWAYS DO

17. **Always return a partial `dict` from nodes** — Only changed keys.
18. **Always pass `trace_id` to tracer calls** — Observability requires trace correlation.
19. **Always pass `action="dispatch"` to `agent()`** — Required for LLM calls.
20. **Always pass `task=`=user instruction, `context=`=system prompt to `agent()`** — The correct mapping for synthesis/evaluate. [v1.1/P0 #2]
21. **Always decrement Tavily budget on ATTEMPT** — Paid API charges per call regardless of outcome. [v1.1/P0 #4]
22. **Always surface collected citations in `_node_report`** — Append a `## Sources` section from `citations.get_sources(tid)`. [v1.1]
23. **Always return source URLs as `artifacts` from `_node_notify`** — `artifacts = [s["url"] for s in citations.get_sources(tid)]`. [v1.1]
24. **Always wrap `memory.*` and `notify()` in `try/except` + `tracer.error`** — Non-fatal; the workflow must continue.
25. **Always store the full result in `_node_store`** — No `[:800]` truncation. [v1.1/P1 #10]
26. **Always test `route_after_synthesize` with all paths** — Assert `"report"` (hard cap, stuck, dual-gate) and `"decompose"` (continue).
27. **Always test budget: web must NOT decrement, Tavily MUST decrement on attempt.** [v1.1/P0 #4]
28. **Always update this doc** when adding nodes, changing routing logic, or modifying error handling.

---

## 🚫 Anti-Patterns & Lessons Learned

> - **What happened:** `task`/`content` were swapped in `node_synthesize` — `task=` held the system prompt, `content=` held the user instruction.
> - **Why it matters:** `task` → `llm.complete(user=task)`, so the system prompt text landed in the user slot, and the actual synthesis instruction (goal+evidence) went to `content=` (tertiary). The role's configured system prompt then overrode the intended framing entirely.
> - **Fix:** `task=`=user instruction (goal + evidence), `context=`=system framing prompt. [v1.1/P0 #2]

> - **What happened:** API budget was decremented only on Tavily SUCCESS. Failed Tavily calls consumed real API quota but never reduced the tracker.
> - **Why it matters:** The workflow kept retrying Tavily thinking it had budget headroom, when in fact the quota was already exhausted by failed calls.
> - **Fix:** Decrement on ATTEMPT — Tavily is a paid API that charges per call regardless of outcome. [v1.1/P0 #4]

> - **What happened:** Citations were collected by `node_search` via `citations.add()` but never read back. `_node_report` built the report from synthesis/knowledge_base only; `_node_notify` returned no artifacts.
> - **Why it matters:** Users got a research report with no source attribution — the entire citation tracker was dead infrastructure for this workflow.
> - **Fix:** `_node_report` appends a `## Sources` section; `_node_notify` returns source URLs as `artifacts`. [v1.1]

> - **What happened:** `_node_store` stored `result[:800]` in semantic memory. Long research results were truncated to a tiny fraction.
> - **Why it matters:** Semantic memory is for content retrieval; truncation made it nearly useless for long research.
> - **Fix:** Store the full result. Same fix as the research workflow #7. [v1.1/P1 #10]

> - **What happened:** `_node_recall` silently caught memory failures and returned empty context — no trace step, no error log.
> - **Why it matters:** A chromadb outage was invisible; the workflow appeared to simply have no relevant memories.
> - **Fix:** `try/except` + `tracer.error(tid, "recall", ...)`. Non-fatal, but observable. [v1.1/P1 #8]

> - **What happened:** `decrement_api_calls()` was called for ALL successful searches, including web (SearXNG). Web is free.
> - **Why it matters:** API budget exhausted prematurely; a 20-call Tavily budget was consumed by free web searches.
> - **Fix:** Guard with `if actual_tool == "tavily":`. [v1.0.2]

> - **What happened:** Both `agent()` calls in `node_synthesize` were missing `action="dispatch"`. The facade returned "Unknown action" error.
> - **Why it matters:** Synthesis fell back to `prev_knowledge` (always `""` on first iteration); evaluate always returned `score=0.0`. Knowledge base never advanced.
> - **Fix:** Add `action="dispatch"` as the first keyword argument. [v1.0.1]

---

*Last updated: 2026-07-14 (v1.1.1). See [ARCHITECTURE.md](ARCHITECTURE.md) for file maps, [API.md](API.md) for node details, [CHANGELOG.md](CHANGELOG.md) for version history.*
